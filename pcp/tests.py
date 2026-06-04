from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from pcp.models import (
    MovimentacaoEstoquePCP,
    OrigemMovimentacao,
    PcpAlertaEnviado,
    PcpAreaProducao,
    PcpAtivo,
    PcpExecucaoManutencao,
    PcpEvidenciaManutencao,
    PcpEventoAuditoriaManutencao,
    PcpParametroAlerta,
    PcpPlanoManutencao,
    PcpProgramacaoAlertaManutencao,
    StatusAlerta,
    StatusAtivo,
    StatusManutencao,
    TipoManutencao,
    TipoMovimentacao,
)
from pcp.services import (
    AlertaManutencaoService,
    DowntimeService,
    EvidenciaManutencaoService,
    PCPEstoqueETLService,
    PlanoManutencaoService,
    ProgramacaoManutencaoService,
)
from pcp.services.exceptions import PcpConflictError, PcpValidationError


class PcpMaintenanceServicesTests(TestCase):
    def setUp(self) -> None:
        self.area = PcpAreaProducao.objects.create(codigo="LINHA-01", nome="Linha 01")
        self.ativo = PcpAtivo.objects.create(codigo="MAQ-001", nome="Centro de Usinagem", area=self.area)

    def test_criar_plano_exige_intervalo_valido(self) -> None:
        with self.assertRaises(PcpValidationError):
            PlanoManutencaoService.criar_plano(
                ativo_pcp=self.ativo,
                nome="Preventiva mensal",
                tipo=TipoManutencao.PREVENTIVA,
            )

    def test_recalculo_diario_mantem_uma_programacao_pendente(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva mensal",
            intervalo_dias=30,
        )

        primeira = ProgramacaoManutencaoService.gerar_proxima_preventiva(
            plano=plano,
            referencia=date(2026, 6, 3),
        )
        segunda = ProgramacaoManutencaoService.gerar_proxima_preventiva(
            plano=plano,
            referencia=date(2026, 6, 4),
        )

        self.assertTrue(primeira.criada)
        self.assertFalse(segunda.criada)
        self.assertEqual(primeira.programacao.pk, segunda.programacao.pk)
        self.assertEqual(primeira.programacao.data_prevista, date(2026, 7, 3))
        self.assertEqual(plano.programacoes.count(), 1)

    def test_concluir_execucao_gera_proxima_programacao(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva mensal",
            intervalo_dias=30,
        )
        programacao = ProgramacaoManutencaoService.gerar_proxima_preventiva(
            plano=plano,
            referencia=date(2026, 6, 3),
        ).programacao
        inicio = timezone.now()
        execucao = PcpExecucaoManutencao.objects.create(
            programacao=programacao,
            ativo_pcp=self.ativo,
            tipo=TipoManutencao.PREVENTIVA,
            data_inicio=inicio,
        )

        ProgramacaoManutencaoService.concluir_execucao(
            execucao=execucao,
            data_fim=inicio + timedelta(hours=1),
        )

        programacao.refresh_from_db()
        self.assertEqual(programacao.status, StatusManutencao.CONCLUIDA)
        self.assertEqual(plano.programacoes.filter(status=StatusManutencao.PLANEJADA).count(), 1)
        execucao.refresh_from_db()
        self.assertEqual(execucao.snapshot_ativo_codigo, self.ativo.codigo)
        self.assertEqual(execucao.snapshot_plano_nome, plano.nome)
        self.assertIsNotNone(execucao.concluido_em)
        self.assertTrue(execucao.eventos_auditoria.filter(tipo_evento="concluida").exists())

    def test_downtime_abertura_e_fechamento_calculam_duracao_e_status(self) -> None:
        inicio = timezone.now()
        downtime = DowntimeService.abrir_downtime(ativo_pcp=self.ativo, motivo="Falha eletrica", inicio=inicio)

        with self.assertRaises(PcpConflictError):
            DowntimeService.abrir_downtime(ativo_pcp=self.ativo, motivo="Segunda falha", inicio=inicio)

        fechado = DowntimeService.fechar_downtime(downtime=downtime, fim=inicio + timedelta(minutes=91))
        self.ativo.refresh_from_db()

        self.assertEqual(fechado.duracao_minutos, 91)
        self.assertEqual(self.ativo.status, StatusAtivo.OPERANDO)

    def test_soft_delete_remove_do_manager_padrao_sem_excluir_registro(self) -> None:
        ativo_id = self.ativo.id
        self.ativo.delete()

        self.assertFalse(PcpAtivo.objects.filter(id=ativo_id).exists())
        self.assertTrue(PcpAtivo.all_objects.filter(id=ativo_id, ativo=False).exists())

    def test_all_objects_tambem_aplica_soft_delete_em_lote(self) -> None:
        ativo_id = self.ativo.id
        PcpAtivo.all_objects.filter(id=ativo_id).delete()

        self.assertFalse(PcpAtivo.objects.filter(id=ativo_id).exists())
        self.assertTrue(PcpAtivo.all_objects.filter(id=ativo_id, ativo=False).exists())

    def test_parametro_alerta_nao_aceita_area_e_ativo_simultaneamente(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            PcpParametroAlerta.objects.create(
                ativo_pcp=self.ativo,
                area=self.area,
                emails_destino="pcp@example.com",
            )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        PCP_MAINTENANCE_ALERT_RECIPIENTS=["pcp@example.com"],
    )
    def test_alerta_preventiva_usa_marcos_fixos_e_e_idempotente(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva mensal",
            intervalo_dias=30,
        )
        referencia = date(2026, 6, 3)
        programacao = ProgramacaoManutencaoService.gerar_proxima_preventiva(
            plano=plano,
            referencia=referencia,
        ).programacao

        primeiro_envio = AlertaManutencaoService.enviar_alertas_preventivas(referencia=referencia)
        segundo_envio = AlertaManutencaoService.enviar_alertas_preventivas(referencia=referencia)
        envio_recuperado = AlertaManutencaoService.enviar_alertas_preventivas(
            referencia=referencia + timedelta(days=16)
        )

        alerta = PcpAlertaEnviado.objects.get(programacao_alerta__dias_antecedencia=30)
        agendamentos = PcpProgramacaoAlertaManutencao.objects.filter(programacao=programacao)
        self.assertEqual(primeiro_envio, 1)
        self.assertEqual(segundo_envio, 0)
        self.assertEqual(envio_recuperado, 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(alerta.status, StatusAlerta.ENVIADO)
        self.assertEqual(alerta.tentativas, 1)
        self.assertEqual(set(agendamentos.values_list("dias_antecedencia", flat=True)), {30, 15, 7, 1})
        self.assertEqual(agendamentos.get(dias_antecedencia=30).status, StatusAlerta.ENVIADO)
        self.assertEqual(agendamentos.get(dias_antecedencia=15).status, StatusAlerta.ENVIADO)

    def test_evento_auditoria_nao_pode_ser_alterado_ou_excluido(self) -> None:
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=self.ativo,
            tipo=TipoManutencao.CORRETIVA,
        )
        evento = execucao.eventos_auditoria.get()

        with self.assertRaises(ValueError):
            evento.delete()
        with self.assertRaises(ValueError):
            PcpEventoAuditoriaManutencao.objects.filter(pk=evento.pk).update(justificativa="alterado")

    def test_evidencia_pdf_e_validada_e_auditada(self) -> None:
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=self.ativo,
            tipo=TipoManutencao.CORRETIVA,
        )
        arquivo = SimpleUploadedFile("laudo.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")

        evidencia = EvidenciaManutencaoService.adicionar(
            execucao=execucao,
            arquivo=arquivo,
            usuario=None,
            descricao="Laudo tecnico",
        )

        self.assertEqual(evidencia.tipo, "pdf")
        self.assertEqual(len(evidencia.sha256), 64)
        self.assertTrue(execucao.eventos_auditoria.filter(tipo_evento="evidencia_adicionada").exists())
        EvidenciaManutencaoService.desativar(
            evidencia=evidencia,
            usuario=None,
            justificativa="Documento substituido.",
        )
        self.assertFalse(PcpEvidenciaManutencao.objects.filter(pk=evidencia.pk).exists())
        self.assertTrue(PcpEvidenciaManutencao.all_objects.filter(pk=evidencia.pk, ativo=False).exists())
        self.assertTrue(evidencia.arquivo.storage.exists(evidencia.arquivo.name))
        self.assertTrue(execucao.eventos_auditoria.filter(tipo_evento="evidencia_desativada").exists())
        evidencia.arquivo.storage.delete(evidencia.arquivo.name)


class PcpEstoqueETLTests(TestCase):
    def test_etl_processa_chaves_minusculas_e_diferencia_tipo_movimentacao(self) -> None:
        sd1 = pd.DataFrame(
            [
                {
                    "D1_FILIAL": "01",
                    "D1_COD": "PROD-1",
                    "D1_DTDIGIT": "20260603",
                    "D1_QUANT": "10.5",
                    "D1_DOC": "100",
                }
            ]
        )
        sd3 = pd.DataFrame(
            [
                {
                    "D3_FILIAL": "01",
                    "D3_COD": "PROD-1",
                    "D3_EMISSAO": "20260603",
                    "D3_QUANT": "2",
                    "D3_DOC": "200",
                    "D3_TM": "RE",
                    "D3_CF": "001",
                },
                {
                    "D3_FILIAL": "01",
                    "D3_COD": "PROD-1",
                    "D3_EMISSAO": "20260603",
                    "D3_QUANT": "1",
                    "D3_DOC": "200",
                    "D3_TM": "DE",
                    "D3_CF": "001",
                },
            ]
        )

        processado = PCPEstoqueETLService.transformar_e_salvar({"sd1": sd1, "sd3": sd3})

        self.assertTrue(processado)
        self.assertEqual(MovimentacaoEstoquePCP.objects.count(), 3)
        self.assertTrue(
            MovimentacaoEstoquePCP.objects.filter(
                origem_movimentacao=OrigemMovimentacao.MOV_INTERNA,
                tipo_movimentacao=TipoMovimentacao.SAIDA,
            ).exists()
        )
        self.assertTrue(
            MovimentacaoEstoquePCP.objects.filter(
                origem_movimentacao=OrigemMovimentacao.MOV_INTERNA,
                tipo_movimentacao=TipoMovimentacao.ENTRADA,
            ).exists()
        )


class PcpOperationalApiTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="pcp_user",
            email="pcp_user@example.com",
            password="senha-forte-123",
        )
        self.user_sem_grupo = user_model.objects.create_user(
            username="sem_grupo",
            email="sem_grupo@example.com",
            password="senha-forte-123",
        )
        grupo_pcp, _ = Group.objects.get_or_create(name="PCP")
        self.user.groups.add(grupo_pcp)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.area = PcpAreaProducao.objects.create(codigo="LINHA-API", nome="Linha API")
        self.ativo = PcpAtivo.objects.create(codigo="MAQ-API", nome="Maquina API", area=self.area)

    def test_api_bloqueia_usuario_autenticado_sem_grupo_pcp(self) -> None:
        self.client.force_authenticate(user=self.user_sem_grupo)
        response = self.client.get("/api/pcp/ativos/")
        self.assertEqual(response.status_code, 403)

    def test_api_rejeita_filtro_invalido(self) -> None:
        response = self.client.get("/api/pcp/programacoes-manutencao/?data_inicio=invalida")
        self.assertEqual(response.status_code, 400)

    def test_api_abre_e_fecha_downtime_via_services(self) -> None:
        inicio = timezone.now()
        response = self.client.post(
            "/api/pcp/downtimes/",
            {"ativo_pcp": self.ativo.id, "motivo": "Falha API", "inicio": inicio.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        downtime_id = response.data["id"]
        response = self.client.post(
            f"/api/pcp/downtimes/{downtime_id}/fechar/",
            {"fim": (inicio + timedelta(minutes=45)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["duracao_minutos"], 45)

    def test_api_inicia_e_conclui_execucao_de_manutencao(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva API",
            intervalo_dias=30,
        )
        programacao = ProgramacaoManutencaoService.gerar_proxima_preventiva(
            plano=plano,
            referencia=date(2026, 6, 3),
        ).programacao
        inicio = timezone.now()

        response = self.client.post(
            "/api/pcp/execucoes-manutencao/",
            {
                "ativo_pcp": self.ativo.id,
                "programacao": programacao.id,
                "tipo": TipoManutencao.PREVENTIVA,
                "data_inicio": inicio.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        execucao_id = response.data["id"]
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.MANUTENCAO)

        response = self.client.post(
            f"/api/pcp/execucoes-manutencao/{execucao_id}/concluir/",
            {"data_fim": (inicio + timedelta(hours=1)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.OPERANDO)

    @override_settings(POWER_BI_API_KEY="segredo-power-bi")
    def test_api_power_bi_exige_chave_e_retorna_filial(self) -> None:
        MovimentacaoEstoquePCP.objects.create(
            filial="01",
            produto_codigo="PROD-API",
            data_movimentacao=date(2026, 6, 3),
            tipo_movimentacao=TipoMovimentacao.ENTRADA,
            origem_movimentacao=OrigemMovimentacao.NF_ENTRADA,
            quantidade=10,
        )

        negado = self.client.get("/api/pcp/powerbi/movimentacoes/")
        autorizado = self.client.get(
            "/api/pcp/powerbi/movimentacoes/",
            HTTP_AUTHORIZATION="Api-Key segredo-power-bi",
        )

        self.assertEqual(negado.status_code, 403)
        self.assertEqual(autorizado.status_code, 200)
        self.assertEqual(autorizado.data["results"][0]["filial"], "01")


class PcpDashboardViewTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="pcp_dashboard",
            email="pcp_dashboard@example.com",
            password="senha-forte-123",
        )
        grupo_pcp, _ = Group.objects.get_or_create(name="PCP")
        self.user.groups.add(grupo_pcp)
        self.client.force_login(self.user)

    def test_dashboard_pcp_renderiza_para_usuario_do_grupo_pcp(self) -> None:
        response = self.client.get("/pcp/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pcp/dashboard.html")
        self.assertContains(response, "Dashboard PCP")
        self.assertContains(response, "Gestão de ativos, downtimes e preventivas de produção.")
        self.assertNotContains(response, "GestÃ")


class PcpAssetViewsTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="pcp_ativos",
            email="pcp_ativos@example.com",
            password="senha-forte-123",
        )
        self.user_sem_grupo = user_model.objects.create_user(
            username="pcp_ativos_sem_grupo",
            email="pcp_ativos_sem_grupo@example.com",
            password="senha-forte-123",
        )
        grupo_pcp, _ = Group.objects.get_or_create(name="PCP")
        self.user.groups.add(grupo_pcp)
        self.area = PcpAreaProducao.objects.create(codigo="AREA-TELA", nome="Area Tela")
        self.client.force_login(self.user)

    def test_tela_cadastra_e_exibe_ativo(self) -> None:
        response = self.client.post(
            "/pcp/ativos/novo/",
            {
                "codigo": "maq-tela-01",
                "nome": "Maquina da Tela",
                "area": self.area.pk,
                "descricao": "Ativo cadastrado pela interface.",
                "fabricante": "I9",
                "modelo": "M1",
                "numero_serie": "SERIE-01",
                "criticidade": "alta",
            },
        )

        ativo = PcpAtivo.objects.get(codigo="MAQ-TELA-01")
        self.assertRedirects(response, f"/pcp/ativos/{ativo.pk}/")
        detalhe = self.client.get(f"/pcp/ativos/{ativo.pk}/")
        self.assertContains(detalhe, "Maquina da Tela")
        self.assertContains(detalhe, "Histórico de manutenções")

    def test_download_evidencia_exige_acesso_ao_modulo(self) -> None:
        ativo = PcpAtivo.objects.create(codigo="MAQ-DOC", nome="Maquina Documento", area=self.area)
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
        )
        evidencia = EvidenciaManutencaoService.adicionar(
            execucao=execucao,
            arquivo=SimpleUploadedFile("laudo.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            usuario=self.user,
        )

        self.client.force_login(self.user_sem_grupo)
        negado = self.client.get(f"/pcp/evidencias/{evidencia.pk}/download/")
        self.assertEqual(negado.status_code, 302)

        self.client.force_login(self.user)
        autorizado = self.client.get(f"/pcp/evidencias/{evidencia.pk}/download/")
        self.assertEqual(autorizado.status_code, 200)
        for fechar_recurso in autorizado._resource_closers:
            fechar_recurso()
        autorizado._resource_closers.clear()
        evidencia.arquivo.storage.delete(evidencia.arquivo.name)

    def test_tela_inicia_e_conclui_manutencao_documentada(self) -> None:
        ativo = PcpAtivo.objects.create(codigo="MAQ-MAN", nome="Maquina Manutencao", area=self.area)

        inicio = self.client.post(
            f"/pcp/ativos/{ativo.pk}/manutencoes/nova/",
            {"tipo": TipoManutencao.CORRETIVA, "programacao": "", "observacao": "Falha identificada"},
        )
        execucao = PcpExecucaoManutencao.objects.get(ativo_pcp=ativo)
        self.assertRedirects(inicio, f"/pcp/manutencoes/{execucao.pk}/")

        conclusao = self.client.post(
            f"/pcp/manutencoes/{execucao.pk}/concluir/",
            {
                "data_fim": "",
                "diagnostico": "Falha eletrica",
                "servicos_executados": "Substituicao do componente",
                "resultado": "Equipamento liberado",
                "recomendacoes": "Inspecionar em sete dias",
            },
        )

        execucao.refresh_from_db()
        self.assertRedirects(conclusao, f"/pcp/manutencoes/{execucao.pk}/")
        self.assertIsNotNone(execucao.data_fim)
        self.assertEqual(execucao.concluido_por, self.user)
        self.assertEqual(execucao.servicos_executados, "Substituicao do componente")
