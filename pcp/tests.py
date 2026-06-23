from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from pcp.forms import PcpPlanoManutencaoForm
from pcp.models import (
    CategoriaDowntime,
    FinalidadeEvidencia,
    MovimentacaoEstoquePCP,
    OrigemMovimentacao,
    PcpAlertaEnviado,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpEvidenciaManutencao,
    PcpEventoAuditoriaManutencao,
    PcpItemManutencao,
    PcpParametroAlerta,
    PcpPlanoManutencao,
    PcpPlanoManutencaoItem,
    PcpProgramacaoAlertaManutencao,
    StatusAlerta,
    StatusAtivo,
    StatusManutencao,
    TipoDowntime,
    TipoManutencao,
    TipoMovimentacao,
)
from pcp.services import (
    AlertaManutencaoService,
    AtivoService,
    DowntimeService,
    DowntimeAnalyticsService,
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
                data_inicio=date(2026, 6, 3),
                tipo=TipoManutencao.PREVENTIVA,
            )

    def test_recalculo_diario_mantem_uma_programacao_pendente(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva mensal",
            intervalo_dias=30,
            data_inicio=date(2026, 6, 3),
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
        self.assertEqual(primeira.programacao.data_prevista, date(2026, 6, 3))
        self.assertEqual(plano.programacoes.count(), 1)

    def test_concluir_execucao_gera_proxima_programacao(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva mensal",
            intervalo_dias=30,
            data_inicio=date(2026, 6, 3),
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
        proxima = plano.programacoes.get(status=StatusManutencao.PLANEJADA)
        self.assertEqual(
            proxima.data_prevista,
            timezone.localtime(inicio + timedelta(hours=1)).date() + timedelta(days=30),
        )

    def test_downtime_abertura_e_fechamento_calculam_duracao_e_status(self) -> None:
        inicio = timezone.now()
        downtime = DowntimeService.abrir_downtime(ativo_pcp=self.ativo, motivo="Falha eletrica", inicio=inicio)
        self.ativo.refresh_from_db()
        self.assertEqual(self.ativo.status, StatusAtivo.PARADO)

        with self.assertRaises(PcpConflictError):
            DowntimeService.abrir_downtime(ativo_pcp=self.ativo, motivo="Segunda falha", inicio=inicio)

        fechado = DowntimeService.fechar_downtime(downtime=downtime, fim=inicio + timedelta(minutes=91))
        self.ativo.refresh_from_db()

        self.assertEqual(fechado.duracao_minutos, 91)
        self.assertEqual(fechado.categoria, CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO)
        self.assertEqual(fechado.tipo, TipoDowntime.MAQUINARIO_ESTRAGOU)
        self.assertEqual(self.ativo.status, StatusAtivo.OPERANDO)

    def test_downtime_deriva_tempo_ocioso_por_falta_de_desenho(self) -> None:
        downtime = DowntimeService.abrir_downtime(
            ativo_pcp=self.ativo,
            tipo=TipoDowntime.FALTA_DESENHO,
            motivo="Projeto ainda não liberado.",
        )

        self.assertEqual(downtime.categoria, CategoriaDowntime.TEMPO_OCIOSO)

    def test_downtime_rejeita_tipo_legado_em_novo_registro(self) -> None:
        with self.assertRaisesMessage(PcpValidationError, "Tipo de parada inválido."):
            DowntimeService.abrir_downtime(
                ativo_pcp=self.ativo,
                tipo="nao_planejado",
                motivo="Tipo legado",
            )

    def test_analytics_recorta_periodo_e_inclui_parada_aberta(self) -> None:
        fim_periodo = timezone.now().replace(microsecond=0)
        inicio_periodo = fim_periodo - timedelta(days=1)
        outro_ativo = PcpAtivo.objects.create(codigo="MAQ-002", nome="Torno", area=self.area)
        PcpDowntime.objects.create(
            ativo_pcp=self.ativo,
            categoria=CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO,
            tipo=TipoDowntime.FALTA_MAO_OBRA,
            inicio=inicio_periodo - timedelta(hours=1),
            fim=inicio_periodo + timedelta(hours=2),
            duracao_minutos=180,
            motivo="Operador ausente",
        )
        PcpDowntime.objects.create(
            ativo_pcp=outro_ativo,
            categoria=CategoriaDowntime.TEMPO_OCIOSO,
            tipo=TipoDowntime.FALTA_DESENHO,
            inicio=fim_periodo - timedelta(hours=1),
            motivo="Desenho não liberado",
        )

        analytics = DowntimeAnalyticsService.analisar_periodo(inicio=inicio_periodo, fim=fim_periodo)

        categorias = {item["codigo"]: item for item in analytics["categorias"]}
        motivos = {item["tipo"]: item for item in analytics["motivos"]}
        self.assertEqual(analytics["total"]["minutos"], 180)
        self.assertEqual(categorias[CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO]["minutos"], 120)
        self.assertEqual(categorias[CategoriaDowntime.TEMPO_OCIOSO]["minutos"], 60)
        self.assertTrue(motivos[TipoDowntime.FALTA_MAO_OBRA]["destaque"])
        self.assertTrue(motivos[TipoDowntime.FALTA_DESENHO]["destaque"])

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
            data_inicio=date(2026, 7, 3),
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
        self.assertEqual(evidencia.finalidade, FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO)
        self.assertEqual(len(evidencia.sha256), 64)
        evento = execucao.eventos_auditoria.get(tipo_evento="evidencia_adicionada")
        self.assertEqual(evento.dados["finalidade"], FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO)
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

    def test_corrigir_execucao_concluida_exige_justificativa_e_audita(self) -> None:
        inicio = timezone.now()
        execucao = PcpExecucaoManutencao.objects.create(
            ativo_pcp=self.ativo,
            tipo=TipoManutencao.CORRETIVA,
            data_inicio=inicio,
            data_fim=inicio + timedelta(hours=1),
            diagnostico="Diagnostico inicial",
            servicos_executados="Servico inicial",
            resultado="Liberado",
        )

        with self.assertRaises(PcpValidationError):
            ProgramacaoManutencaoService.corrigir_execucao_concluida(
                execucao=execucao,
                usuario=None,
                justificativa="",
                diagnostico="Diagnóstico revisado",
            )

        corrigida = ProgramacaoManutencaoService.corrigir_execucao_concluida(
            execucao=execucao,
            usuario=None,
            justificativa="Correção de laudo técnico.",
            diagnostico="Diagnóstico revisado",
            servicos_executados="Serviço inicial",
            resultado="Liberado",
        )

        self.assertEqual(corrigida.diagnostico, "Diagnóstico revisado")
        self.assertTrue(corrigida.eventos_auditoria.filter(tipo_evento="corrigida").exists())


class PcpPlanoManutencaoFormTests(TestCase):
    def setUp(self) -> None:
        self.area = PcpAreaProducao.objects.create(codigo="LINHA-FORM", nome="Linha Form")
        self.ativo = PcpAtivo.objects.create(codigo="MAQ-FORM", nome="Maquina Form", area=self.area)

    def test_novo_plano_exibe_apenas_tipos_permitidos(self) -> None:
        form = PcpPlanoManutencaoForm(ativo=self.ativo)

        choices = {valor for valor, _label in form.fields["tipo"].choices}

        self.assertIn(TipoManutencao.PREVENTIVA, choices)
        self.assertIn(TipoManutencao.CORRETIVA, choices)
        self.assertNotIn(TipoManutencao.PREDITIVA, choices)
        self.assertNotIn(TipoManutencao.INSPECAO, choices)

    def test_novo_plano_nao_aceita_tipo_legado_em_post_manual(self) -> None:
        form = PcpPlanoManutencaoForm(
            data={
                "tipo": TipoManutencao.PREDITIVA,
                "nome": "Plano legado manual",
                "descricao": "",
                "intervalo_dias": 30,
                "data_inicio": "2026-07-01",
            },
            ativo=self.ativo,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("tipo", form.errors)

    def test_edicao_de_plano_legado_mantem_tipo_atual_visivel(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Plano legado",
            tipo=TipoManutencao.INSPECAO,
            intervalo_dias=30,
            data_inicio=date(2026, 7, 1),
        )

        form = PcpPlanoManutencaoForm(instance=plano, ativo=self.ativo)
        choices = {valor for valor, _label in form.fields["tipo"].choices}

        self.assertIn(TipoManutencao.INSPECAO, choices)
        self.assertIn(TipoManutencao.PREVENTIVA, choices)
        self.assertIn(TipoManutencao.CORRETIVA, choices)


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

    @override_settings(PCP_DEFAULT_AREA_CODE="FABRICA-UNICA", PCP_DEFAULT_AREA_NAME="Fábrica Única")
    def test_api_cadastra_ativo_na_area_tecnica_padrao(self) -> None:
        response = self.client.post(
            "/api/pcp/ativos/",
            {"codigo": "maq-api-nova", "nome": "Máquina API Nova", "criticidade": "alta"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["area_codigo"], "FABRICA-UNICA")
        self.assertEqual(response.data["area_nome"], "Fábrica Única")

    def test_api_plano_exige_data_inicio(self) -> None:
        response = self.client.post(
            "/api/pcp/planos-manutencao/",
            {
                "ativo_pcp": self.ativo.id,
                "nome": "Plano sem início",
                "tipo": TipoManutencao.PREVENTIVA,
                "intervalo_dias": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("data_inicio", response.data)

    def test_api_abre_e_fecha_downtime_via_services(self) -> None:
        inicio = timezone.now()
        response = self.client.post(
            "/api/pcp/downtimes/",
            {"ativo_pcp": self.ativo.id, "motivo": "Falha API", "inicio": inicio.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["categoria"], CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO)
        self.assertEqual(response.data["tipo"], TipoDowntime.MAQUINARIO_ESTRAGOU)
        self.assertEqual(response.data["categoria_descricao"], "Tempo de Produção (Perdido)")
        downtime_id = response.data["id"]
        response = self.client.post(
            f"/api/pcp/downtimes/{downtime_id}/fechar/",
            {"fim": (inicio + timedelta(minutes=45)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["duracao_minutos"], 45)

    def test_api_filtra_downtime_por_categoria(self) -> None:
        DowntimeService.abrir_downtime(
            ativo_pcp=self.ativo,
            tipo=TipoDowntime.FALTA_DESENHO,
            motivo="Desenho pendente",
            responsavel=self.user,
        )

        ociosos = self.client.get(
            "/api/pcp/downtimes/",
            {"categoria": CategoriaDowntime.TEMPO_OCIOSO},
        )
        producao = self.client.get(
            "/api/pcp/downtimes/",
            {"categoria": CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO},
        )

        self.assertEqual(ociosos.status_code, 200)
        self.assertEqual(ociosos.data["count"], 1)
        self.assertEqual(producao.data["count"], 0)

    def test_api_inicia_e_conclui_execucao_de_manutencao(self) -> None:
        plano = PcpPlanoManutencao.objects.create(
            ativo_pcp=self.ativo,
            nome="Preventiva API",
            intervalo_dias=30,
            data_inicio=date(2026, 6, 3),
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
        self.assertContains(response, "Gestão de Ativos")
        self.assertContains(response, "Visão operacional de disponibilidade, paradas e manutenções programadas.")
        self.assertContains(response, "Análise de tempo perdido")
        self.assertContains(response, "Tempo de Produção (Perdido)")
        self.assertContains(response, "Tempo Ocioso")
        self.assertNotContains(response, "GestÃ")


    def test_dashboard_usa_90_dias_por_padrao_e_nome_do_ativo_no_grafico(self) -> None:
        area = PcpAreaProducao.objects.create(codigo="AREA-GRAFICO", nome="Área do gráfico")
        ativo = PcpAtivo.objects.create(codigo="MAQ-GRAFICO", nome="Prensa Hidráulica", area=area)
        fim = timezone.now() - timedelta(hours=1)
        PcpDowntime.objects.create(
            ativo_pcp=ativo,
            categoria=CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO,
            tipo=TipoDowntime.MAQUINARIO_ESTRAGOU,
            inicio=fim - timedelta(hours=2),
            fim=fim,
            duracao_minutos=120,
            motivo="Falha mecânica",
        )

        response = self.client.get("/pcp/dashboard/")

        self.assertEqual(response.context["dias"], 90)
        self.assertEqual(response.context["top_downtime_labels"], ["Prensa Hidráulica"])
        self.assertContains(response, "180 dias")
        self.assertContains(response, "365 dias")

    def test_dashboard_aceita_periodos_de_180_e_365_dias(self) -> None:
        for periodo in (180, 365):
            with self.subTest(periodo=periodo):
                response = self.client.get("/pcp/dashboard/", {"periodo": periodo})
                self.assertEqual(response.context["dias"], periodo)


class PcpDowntimeCategoriaMigrationTests(TransactionTestCase):
    migrate_from = ("pcp", "0010_pcpplanomanutencao_data_inicio")
    migrate_to = ("pcp", "0011_pcpdowntime_categoria")

    def setUp(self) -> None:
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        apps = executor.loader.project_state([self.migrate_from]).apps
        area_model = apps.get_model("pcp", "PcpAreaProducao")
        ativo_model = apps.get_model("pcp", "PcpAtivo")
        downtime_model = apps.get_model("pcp", "PcpDowntime")
        area = area_model.objects.create(codigo="LEGADO", nome="Área Legada")
        ativo = ativo_model.objects.create(codigo="MAQ-LEGADA", nome="Máquina Legada", area=area)
        self.downtime_id = downtime_model.objects.create(
            ativo_pcp=ativo,
            tipo="nao_planejado",
            inicio=timezone.now() - timedelta(hours=2),
            fim=timezone.now() - timedelta(hours=1),
            duracao_minutos=60,
            motivo="Registro anterior à categorização",
        ).pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def test_migration_classifica_registro_legado_sem_alterar_tipo(self) -> None:
        downtime_model = self.apps.get_model("pcp", "PcpDowntime")
        downtime = downtime_model._base_manager.get(pk=self.downtime_id)

        self.assertEqual(downtime.categoria, CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO)
        self.assertEqual(downtime.tipo, "nao_planejado")


class PcpEvidenciaFinalidadeMigrationTests(TransactionTestCase):
    migrate_from = ("pcp", "0011_pcpdowntime_categoria")
    migrate_to = ("pcp", "0012_pcpevidenciamanutencao_finalidade")

    def setUp(self) -> None:
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        apps = executor.loader.project_state([self.migrate_from]).apps
        area_model = apps.get_model("pcp", "PcpAreaProducao")
        ativo_model = apps.get_model("pcp", "PcpAtivo")
        execucao_model = apps.get_model("pcp", "PcpExecucaoManutencao")
        evidencia_model = apps.get_model("pcp", "PcpEvidenciaManutencao")
        area = area_model.objects.create(codigo="AREA-EVID-LEGADA", nome="Área legada")
        ativo = ativo_model.objects.create(codigo="MAQ-EVID-LEGADA", nome="Máquina legada", area=area)
        execucao = execucao_model.objects.create(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
            data_inicio=timezone.now(),
        )
        self.evidencia_id = evidencia_model.objects.create(
            execucao=execucao,
            arquivo="manutencoes/legado/laudo.pdf",
            tipo="pdf",
            nome_original="laudo.pdf",
            tipo_mime="application/pdf",
            tamanho_bytes=10,
            sha256="a" * 64,
        ).pk

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def test_migration_classifica_evidencia_legada_como_solucao(self) -> None:
        evidencia_model = self.apps.get_model("pcp", "PcpEvidenciaManutencao")
        evidencia = evidencia_model._base_manager.get(pk=self.evidencia_id)

        self.assertEqual(evidencia.finalidade, FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO)


@override_settings(PCP_DEFAULT_AREA_CODE="FABRICA-UNICA", PCP_DEFAULT_AREA_NAME="Fábrica Única")
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
        self.client.force_login(self.user)

    def test_tela_cadastra_e_exibe_ativo(self) -> None:
        response = self.client.post(
            "/pcp/ativos/novo/",
            {
                "codigo": "maq-tela-01",
                "nome": "Maquina da Tela",
                "descricao": "Ativo cadastrado pela interface.",
                "fabricante": "I9",
                "modelo": "M1",
                "numero_serie": "SERIE-01",
                "criticidade": "alta",
            },
        )

        ativo = PcpAtivo.objects.get(codigo="MAQ-TELA-01")
        self.assertRedirects(response, f"/pcp/ativos/{ativo.pk}/")
        self.assertEqual(ativo.area.codigo, "FABRICA-UNICA")
        self.assertEqual(ativo.area.nome, "Fábrica Única")
        detalhe = self.client.get(f"/pcp/ativos/{ativo.pk}/")
        self.assertContains(detalhe, "Maquina da Tela")
        self.assertContains(detalhe, "Execuções e histórico")

    def test_rotas_visuais_de_area_foram_removidas(self) -> None:
        self.assertEqual(self.client.get("/pcp/areas/").status_code, 404)
        self.assertEqual(self.client.get("/pcp/areas/nova/").status_code, 404)

    def test_tela_exige_data_inicio_para_cadastrar_plano(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-SEM-DATA", nome="Máquina sem data")

        response = self.client.post(
            f"/pcp/ativos/{ativo.pk}/planos/novo/",
            {
                "tipo": TipoManutencao.PREVENTIVA,
                "nome": "Preventiva sem início",
                "descricao": "Plano inválido",
                "intervalo_dias": 30,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este campo é obrigatório.")
        self.assertFalse(PcpPlanoManutencao.objects.filter(ativo_pcp=ativo).exists())

    def test_tela_cadastra_edita_e_desativa_plano_do_ativo(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-PLANO", nome="Máquina Plano")

        response = self.client.post(
            f"/pcp/ativos/{ativo.pk}/planos/novo/",
            {
                "tipo": TipoManutencao.PREVENTIVA,
                "nome": "Preventiva trimestral",
                "descricao": "Plano visual",
                "intervalo_dias": 90,
                "data_inicio": "2026-07-01",
            },
        )

        plano = PcpPlanoManutencao.objects.get(ativo_pcp=ativo)
        self.assertRedirects(response, f"/pcp/ativos/{ativo.pk}/")
        self.assertTrue(plano.programacoes.filter(status=StatusManutencao.PLANEJADA).exists())
        data_original = plano.programacoes.get(status=StatusManutencao.PLANEJADA).data_prevista
        self.assertEqual(data_original, date(2026, 7, 1))

        response = self.client.post(
            f"/pcp/planos/{plano.pk}/editar/",
            {
                "tipo": TipoManutencao.PREVENTIVA,
                "nome": "Preventiva mensal",
                "descricao": "Plano revisado",
                "intervalo_dias": 30,
                "data_inicio": "2026-08-01",
            },
        )
        plano.refresh_from_db()
        self.assertRedirects(response, f"/pcp/ativos/{ativo.pk}/")
        self.assertEqual(plano.nome, "Preventiva mensal")
        self.assertNotEqual(plano.programacoes.get(status=StatusManutencao.PLANEJADA).data_prevista, data_original)

        response = self.client.post(f"/pcp/planos/{plano.pk}/desativar/")
        plano.refresh_from_db()
        self.assertRedirects(response, f"/pcp/ativos/{ativo.pk}/")
        self.assertFalse(plano.ativo)

    def test_preview_pdf_plano_retorna_pdf_inline(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-PDF", nome="Maquina PDF")
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Preventiva PDF",
            data_inicio=date(2026, 7, 1),
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )
        item = PcpItemManutencao.objects.create(
            ativo_pcp=ativo,
            descricao="Lubrificacao dos rolamentos",
        )
        PcpPlanoManutencaoItem.objects.create(plano=plano, item_manutencao=item, ordem=1)
        ProgramacaoManutencaoService.gerar_proxima_preventiva(plano=plano)

        response = self.client.get(f"/pcp/planos/{plano.pk}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_preview_pdf_plano_sem_itens_retorna_pdf_inline(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-PDF-SEM-ITEM", nome="Maquina PDF Sem Item")
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Preventiva PDF Sem Item",
            data_inicio=date(2026, 7, 1),
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )

        response = self.client.get(f"/pcp/planos/{plano.pk}/pdf/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_preview_pdf_plano_exige_grupo_pcp(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-PDF-NEGADO", nome="Maquina PDF Negado")
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Preventiva PDF Negado",
            data_inicio=date(2026, 7, 1),
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )

        self.client.force_login(self.user_sem_grupo)
        response = self.client.get(f"/pcp/planos/{plano.pk}/pdf/")

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.get("Content-Type"), "application/pdf")

    def test_agenda_exibe_programacao_no_periodo_correto(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-AGENDA", nome="Máquina Agenda")
        data_programada = timezone.localdate() + timedelta(days=7)
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Preventiva da agenda",
            data_inicio=data_programada,
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )
        ProgramacaoManutencaoService.gerar_proxima_preventiva(plano=plano)

        response = self.client.get("/pcp/agenda/?periodo=7")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pcp/agenda/lista.html")
        self.assertContains(response, ativo.codigo)
        self.assertContains(response, plano.nome)
        self.assertContains(response, data_programada.strftime("%d/%m/%Y"))

    def test_agenda_usa_90_dias_por_padrao_e_aceita_periodos_maiores(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-AGENDA-LONGA", nome="Máquina Agenda Longa")
        data_programada = timezone.localdate() + timedelta(days=80)
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Preventiva futura",
            data_inicio=data_programada,
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )
        ProgramacaoManutencaoService.gerar_proxima_preventiva(plano=plano)

        response = self.client.get("/pcp/agenda/")

        self.assertEqual(response.context["periodo"], "90")
        self.assertContains(response, ativo.codigo)
        self.assertContains(response, "Próximos 180 dias")
        self.assertContains(response, "Próximos 365 dias")

    def test_historico_pagina_dez_registros_e_exibe_datas(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-HIST-PAG", nome="Máquina Histórico Paginado")
        agora = timezone.now()
        for indice in range(11):
            inicio = agora - timedelta(days=indice + 1, hours=2)
            PcpExecucaoManutencao.objects.create(
                ativo_pcp=ativo,
                tipo=TipoManutencao.CORRETIVA,
                data_inicio=inicio,
                data_fim=inicio + timedelta(hours=1),
            )

        primeira_pagina = self.client.get("/pcp/historico/")
        segunda_pagina = self.client.get("/pcp/historico/", {"page": 2})

        self.assertEqual(len(primeira_pagina.context["execucoes"]), 10)
        self.assertEqual(len(segunda_pagina.context["execucoes"]), 1)
        self.assertContains(primeira_pagina, "Data início")
        self.assertContains(primeira_pagina, "Data término")
        self.assertContains(primeira_pagina, "Página 1 de 2")

    def test_detalhe_ativo_exibe_data_termino_da_execucao(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-FIM", nome="Máquina com Término")
        inicio = timezone.now() - timedelta(hours=2)
        termino = inicio + timedelta(hours=1)
        PcpExecucaoManutencao.objects.create(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
            data_inicio=inicio,
            data_fim=termino,
        )

        response = self.client.get(f"/pcp/ativos/{ativo.pk}/")

        self.assertContains(response, "Data término")
        self.assertContains(response, timezone.localtime(termino).strftime("%d/%m/%Y %H:%M"))

    def test_fluxo_visual_abre_e_fecha_parada_atualizando_status(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-PARADA", nome="Máquina Parada")

        abertura = self.client.post(
            f"/pcp/ativos/{ativo.pk}/paradas/nova/",
            {
                "tipo": TipoDowntime.MAQUINARIO_ESTRAGOU,
                "inicio": "",
                "motivo": "Falha no acionamento",
                "observacao": "Parada registrada pela operação.",
            },
        )
        downtime = PcpDowntime.objects.get(ativo_pcp=ativo, fim__isnull=True)
        ativo.refresh_from_db()

        self.assertRedirects(abertura, f"/pcp/ativos/{ativo.pk}/")
        self.assertEqual(ativo.status, StatusAtivo.PARADO)
        self.assertEqual(downtime.categoria, CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO)

        encerramento = self.client.post(
            f"/pcp/paradas/{downtime.pk}/encerrar/",
            {"fim": "", "observacao": "Máquina liberada para produção."},
        )
        downtime.refresh_from_db()
        ativo.refresh_from_db()

        self.assertRedirects(encerramento, f"/pcp/ativos/{ativo.pk}/")
        self.assertIsNotNone(downtime.fim)
        self.assertEqual(ativo.status, StatusAtivo.OPERANDO)

    def test_formulario_parada_exibe_tipos_agrupados(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-GRUPOS", nome="Máquina Grupos")

        response = self.client.get(f"/pcp/ativos/{ativo.pk}/paradas/nova/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<optgroup label="Tempo de Produção (Perdido)">')
        self.assertContains(response, '<optgroup label="Tempo Ocioso">')
        self.assertContains(response, "Falta de mão de obra")
        self.assertContains(response, "Falta de desenho")
        self.assertNotContains(response, "Não planejado")

    def test_historico_localiza_registro_pelos_snapshots(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-HIST-ANTIGA", nome="Máquina Histórica Antiga")
        plano = PlanoManutencaoService.criar_plano(
            ativo_pcp=ativo,
            nome="Plano Histórico Antigo",
            data_inicio=timezone.localdate(),
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias=30,
        )
        programacao = ProgramacaoManutencaoService.gerar_proxima_preventiva(plano=plano).programacao
        inicio = timezone.now() - timedelta(hours=2)
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=ativo,
            tipo=TipoManutencao.PREVENTIVA,
            data_inicio=inicio,
            responsavel=self.user,
            programacao=programacao,
        )
        ProgramacaoManutencaoService.concluir_execucao(
            execucao=execucao,
            data_fim=inicio + timedelta(hours=1),
            concluido_por=self.user,
            servicos_executados="Inspeção concluída",
            resultado="Ativo liberado",
        )
        PcpAtivo.objects.filter(pk=ativo.pk).update(codigo="MAQ-HIST-NOVA", nome="Máquina Histórica Nova")
        PcpPlanoManutencao.objects.filter(pk=plano.pk).update(nome="Plano Histórico Novo")

        response = self.client.get("/pcp/historico/", {"q": "Histórico Antigo"})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pcp/historico/lista.html")
        self.assertContains(response, "MAQ-HIST-ANTIGA")
        self.assertContains(response, "Plano Histórico Antigo")

    def test_download_evidencia_exige_acesso_ao_modulo(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-DOC", nome="Maquina Documento")
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

    def test_tela_desativa_evidencia_com_permissao_e_justificativa(self) -> None:
        permissao = Permission.objects.get(codename="desativar_evidencia_manutencao")
        self.user.user_permissions.add(permissao)
        ativo = AtivoService.criar_ativo(codigo="MAQ-EVID", nome="Máquina Evidência")
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
        )
        evidencia = EvidenciaManutencaoService.adicionar(
            execucao=execucao,
            arquivo=SimpleUploadedFile("laudo.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            usuario=self.user,
        )

        response = self.client.post(
            f"/pcp/evidencias/{evidencia.pk}/desativar/",
            {"justificativa": "Documento anexado incorretamente."},
        )

        self.assertRedirects(response, f"/pcp/manutencoes/{execucao.pk}/")
        self.assertFalse(PcpEvidenciaManutencao.objects.filter(pk=evidencia.pk).exists())
        self.assertTrue(execucao.eventos_auditoria.filter(tipo_evento="evidencia_desativada").exists())
        evidencia.arquivo.storage.delete(evidencia.arquivo.name)

    def test_tela_registra_evidencias_do_problema_e_da_solucao(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-EVID-DUPLA", nome="Máquina Evidência Dupla")
        execucao = ProgramacaoManutencaoService.iniciar_execucao(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
        )

        response = self.client.post(
            f"/pcp/manutencoes/{execucao.pk}/evidencias/",
            {
                "evidencia_problema": SimpleUploadedFile(
                    "problema.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"
                ),
                "descricao_problema": "Falha antes da intervenção",
                "evidencia_solucao": SimpleUploadedFile(
                    "solucao.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"
                ),
                "descricao_solucao": "Equipamento liberado",
            },
        )

        evidencias = list(PcpEvidenciaManutencao.objects.filter(execucao=execucao).order_by("finalidade"))
        self.assertRedirects(response, f"/pcp/manutencoes/{execucao.pk}/")
        self.assertEqual(len(evidencias), 2)
        self.assertEqual(
            {evidencia.finalidade for evidencia in evidencias},
            {FinalidadeEvidencia.PROBLEMA, FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO},
        )
        self.assertEqual(execucao.eventos_auditoria.filter(tipo_evento="evidencia_adicionada").count(), 2)
        for evidencia in evidencias:
            evidencia.arquivo.storage.delete(evidencia.arquivo.name)

    def test_tela_inicia_e_conclui_manutencao_documentada(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-MAN", nome="Maquina Manutencao")

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

    def test_tela_corrige_manutencao_concluida_somente_com_permissao(self) -> None:
        ativo = AtivoService.criar_ativo(codigo="MAQ-CORR", nome="Máquina Correção")
        inicio = timezone.now()
        execucao = PcpExecucaoManutencao.objects.create(
            ativo_pcp=ativo,
            tipo=TipoManutencao.CORRETIVA,
            data_inicio=inicio,
            data_fim=inicio + timedelta(hours=1),
            diagnostico="Falha inicial",
            servicos_executados="Serviço inicial",
            resultado="Liberado",
        )

        negado = self.client.get(f"/pcp/manutencoes/{execucao.pk}/corrigir/")
        self.assertEqual(negado.status_code, 403)

        permissao = Permission.objects.get(codename="corrigir_execucao_concluida")
        self.user.user_permissions.add(permissao)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        response = self.client.post(
            f"/pcp/manutencoes/{execucao.pk}/corrigir/",
            {
                "observacao": "Observação corrigida",
                "diagnostico": "Falha revisada",
                "servicos_executados": "Serviço revisado",
                "resultado": "Liberado",
                "recomendacoes": "Monitorar por 7 dias",
                "justificativa": "Correção documental solicitada pelo PCP.",
            },
        )

        execucao.refresh_from_db()
        self.assertRedirects(response, f"/pcp/manutencoes/{execucao.pk}/")
        self.assertEqual(execucao.diagnostico, "Falha revisada")
        self.assertTrue(execucao.eventos_auditoria.filter(tipo_evento="corrigida").exists())
