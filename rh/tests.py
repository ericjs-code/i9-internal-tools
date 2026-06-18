from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rh.forms import SolicitacaoVagaForm
from rh.models import AvaliacaoDesempenho, PesquisaDemissional, Vaga
from rh.management.commands.importar_empregados_avaliacao import (
    ImportadorEmpregadosAvaliacao,
    LinhaEmpregado,
    RelatorioImportacao,
)
from rh.services.avaliacoes_desempenho import pode_visualizar_resultado_avaliacao


class SolicitacaoVagaFormTests(TestCase):
    def _dados_validos(self, **overrides):
        dados = {
            'cargo_solicitante': 'Gerente',
            'departamento': Vaga.SETORES.RH,
            'nome_vaga': 'Analista de RH',
            'quantidade_vagas': '1',
            'data_prevista_inicio': '2026-06-22',
            'motivo': 'AUMENTO_FUNC',
            'descricao_atividades': 'Atividades do cargo',
            'sexo': 'INDIFERENTE',
            'escolaridade': 'MEDIO',
            'conhecimentos_desejaveis': 'Conhecimentos',
            'atitudes_desejaveis': 'Atitudes',
        }
        dados.update(overrides)
        return dados

    def test_exige_data_ou_banco_de_talentos(self):
        form = SolicitacaoVagaForm(data=self._dados_validos(data_prevista_inicio=''))

        self.assertFalse(form.is_valid())
        self.assertIn(
            'Informe a data de início previsto ou marque a opção Banco de Talentos.',
            form.non_field_errors(),
        )

    def test_banco_de_talentos_limpa_data_e_permite_sem_previsao(self):
        form = SolicitacaoVagaForm(data=self._dados_validos(
            banco_de_talentos='on',
            data_prevista_inicio='',
        ))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['data_prevista_inicio'])


class PesquisaDemissionalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.usuario_rh = User.objects.create_user(username='rh', password='senha')
        grupo_rh, _ = Group.objects.get_or_create(name='RH')
        self.usuario_rh.groups.add(grupo_rh)

    def _pesquisa(self, **overrides):
        dados = {
            'gerada_por': self.usuario_rh,
            'ex_funcionario_nome': 'Colaborador Teste',
            'setor': Vaga.SETORES.RH,
            'tipo_demissao': 'TERMINO_CONTRATO_TRABALHO',
            'periodo_saida': 'Junho/2026',
            'tempo_casa': '1 ano',
        }
        dados.update(overrides)
        return PesquisaDemissional.objects.create(**dados)

    def test_define_expiracao_ao_criar_pesquisa(self):
        antes = timezone.now() + timedelta(days=15, minutes=-1)
        pesquisa = self._pesquisa()
        depois = timezone.now() + timedelta(days=15, minutes=1)

        self.assertEqual(pesquisa.status, PesquisaDemissional.STATUS.PENDENTE)
        self.assertGreaterEqual(pesquisa.data_expiracao, antes)
        self.assertLessEqual(pesquisa.data_expiracao, depois)

    def test_link_publico_expirado_nao_exibe_formulario(self):
        pesquisa = self._pesquisa(data_expiracao=timezone.now() - timedelta(days=1))

        response = self.client.get(reverse('responder_pesquisa', args=[pesquisa.id_pesquisa]))
        pesquisa.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rh/pesquisa_expirada.html')
        self.assertEqual(pesquisa.status, PesquisaDemissional.STATUS.EXPIRADA)

    def test_gerar_novo_link_preserva_historico(self):
        pesquisa = self._pesquisa(
            status=PesquisaDemissional.STATUS.EXPIRADA,
            data_expiracao=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.usuario_rh)

        response = self.client.post(reverse('gerar_novo_link_pesquisa_demissional', args=[pesquisa.id_pesquisa]))
        nova_pesquisa = PesquisaDemissional.objects.exclude(pk=pesquisa.pk).get()

        self.assertRedirects(response, reverse('listar_pesquisas'))
        self.assertEqual(nova_pesquisa.pesquisa_origem, pesquisa)
        self.assertEqual(nova_pesquisa.status, PesquisaDemissional.STATUS.PENDENTE)
        self.assertGreater(nova_pesquisa.data_expiracao, timezone.now())


class AvaliacaoDesempenhoVisualizacaoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.avaliado = User.objects.create_user(username='avaliado', email='avaliado@example.com', password='senha')
        self.avaliador = User.objects.create_user(username='avaliador', email='avaliador@example.com', password='senha')
        self.outro_usuario = User.objects.create_user(username='outro', email='outro@example.com', password='senha')
        self.admin = User.objects.create_superuser(username='admin', password='senha', email='admin@example.com')
        self.avaliacao = AvaliacaoDesempenho.objects.create(
            avaliado=self.avaliado,
            avaliada_por=self.avaliador,
            ano=2026,
            ciclo=AvaliacaoDesempenho.CICLO.A,
            nome_avaliado='Colaborador Avaliado',
            cargo_avaliado='Analista',
            setor_avaliado='RH',
            status=AvaliacaoDesempenho.STATUS.FINALIZADA,
            comentarios='Comentário visível ao colaborador.',
        )

    def test_avaliado_visualiza_resultado_antes_da_ciencia_do_gestor(self):
        self.assertFalse(self.avaliacao.ciencia_gestor)
        self.assertTrue(pode_visualizar_resultado_avaliacao(self.avaliado, self.avaliacao))
        self.client.force_login(self.avaliado)

        dashboard = self.client.get(reverse('dashboard_avaliacao_desempenho', args=[self.avaliacao.pk]))
        detalhe = self.client.get(reverse('detalhe_avaliacao_desempenho', args=[self.avaliacao.pk]))
        pdf = self.client.get(reverse('exportar_pdf_avaliacao_desempenho', args=[self.avaliacao.pk]))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Comentário visível ao colaborador.')
        self.assertContains(
            dashboard,
            'A ci&ecirc;ncia e concord&acirc;ncia do colaborador ficar&aacute; dispon&iacute;vel',
            html=False,
        )
        self.assertNotContains(dashboard, 'Registrar ci&ecirc;ncia e concord&acirc;ncia como colaborador')
        self.assertEqual(detalhe.status_code, 200)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')

    def test_colaborador_nao_registra_ciencia_antes_do_gestor_via_post(self):
        self.client.force_login(self.avaliado)

        response = self.client.post(reverse('dar_ciencia_colaborador_avaliacao', args=[self.avaliacao.pk]))
        self.avaliacao.refresh_from_db()

        self.assertRedirects(response, reverse('dashboard_avaliacao_desempenho', args=[self.avaliacao.pk]))
        self.assertFalse(self.avaliacao.ciencia_colaborador)
        self.assertEqual(self.avaliacao.status, AvaliacaoDesempenho.STATUS.FINALIZADA)

    def test_ciencia_completa_altera_status_e_remove_edicao_de_gestor_comum(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('dar_ciencia_gestor_avaliacao', args=[self.avaliacao.pk]))
        self.avaliacao.refresh_from_db()
        self.assertTrue(self.avaliacao.ciencia_gestor)
        self.assertEqual(self.avaliacao.status, AvaliacaoDesempenho.STATUS.CIENCIA_PARCIAL)

        self.client.force_login(self.avaliado)
        dashboard = self.client.get(reverse('dashboard_avaliacao_desempenho', args=[self.avaliacao.pk]))
        self.assertContains(dashboard, 'Registrar ci&ecirc;ncia e concord&acirc;ncia como colaborador')

        self.client.post(reverse('dar_ciencia_colaborador_avaliacao', args=[self.avaliacao.pk]))
        self.avaliacao.refresh_from_db()
        self.assertTrue(self.avaliacao.ciencia_colaborador)
        self.assertEqual(self.avaliacao.status, AvaliacaoDesempenho.STATUS.CIENCIA_CONCLUIDA)

    def test_outro_usuario_nao_visualiza_e_avaliado_nao_edita(self):
        self.client.force_login(self.outro_usuario)
        response = self.client.get(reverse('dashboard_avaliacao_desempenho', args=[self.avaliacao.pk]))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.avaliado)
        response = self.client.get(reverse('editar_avaliacao_desempenho', args=[self.avaliacao.pk]))
        self.assertRedirects(response, reverse('dashboard_avaliacao_desempenho', args=[self.avaliacao.pk]))


class ImportadorEmpregadosAvaliacaoSenhaTests(TestCase):
    def _importador(self, **overrides):
        defaults = {
            'caminho': Path('planilha.xlsx'),
            'senha_padrao': 'tmg@2026',
            'dominio_email': 'i9tmg.com.br',
            'atualizar_senha_existentes': False,
            'forcar_troca_senha_existentes': False,
            'permitir_vinculo_admin': False,
            'relatorio': RelatorioImportacao(),
        }
        defaults.update(overrides)
        return ImportadorEmpregadosAvaliacao(**defaults)

    def _linha(self, **overrides):
        defaults = {
            'numero': 23,
            'nome': 'GERSON SENE DE PAULO',
            'admissao': None,
            'cargo': 'Soldador',
            'centro_custo': '',
            'servico': '',
            'departamento': 'PRODUCAO',
            'gestor': 'DANILO',
            'usuario_planilha': '',
            'nome_normalizado': 'GERSON SENE DE PAULO',
            'setor_codigo': Vaga.SETORES.FABRICA,
        }
        defaults.update(overrides)
        return LinhaEmpregado(**defaults)

    def test_usuario_novo_recebe_senha_padrao_e_troca_obrigatoria(self):
        importador = self._importador()

        usuario, criado, senha_definida = importador._buscar_ou_criar_usuario(self._linha(nome='USUARIO NOVO TESTE'))

        self.assertTrue(criado)
        self.assertTrue(senha_definida)
        self.assertTrue(usuario.check_password('tmg@2026'))
        self.assertTrue(usuario.must_change_password)
        self.assertEqual(importador.relatorio.contadores['usuarios_novos_marcados_troca_senha'], 1)

    def test_usuario_existente_sem_flags_nao_altera_senha_nem_troca_obrigatoria(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username='existente',
            email='existente@i9tmg.com.br',
            password='SenhaAtual!2026',
            must_change_password=False,
        )
        importador = self._importador()

        senha_redefinida = importador._aplicar_politica_usuario_existente(usuario)

        usuario.refresh_from_db()
        self.assertFalse(senha_redefinida)
        self.assertTrue(usuario.check_password('SenhaAtual!2026'))
        self.assertFalse(usuario.must_change_password)

    def test_forcar_troca_senha_existente_nao_redefine_senha(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username='existente',
            email='existente@i9tmg.com.br',
            password='SenhaAtual!2026',
            must_change_password=False,
        )
        importador = self._importador(forcar_troca_senha_existentes=True)

        senha_redefinida = importador._aplicar_politica_usuario_existente(usuario)

        usuario.refresh_from_db()
        self.assertFalse(senha_redefinida)
        self.assertTrue(usuario.check_password('SenhaAtual!2026'))
        self.assertTrue(usuario.must_change_password)
        self.assertEqual(importador.relatorio.contadores['usuarios_existentes_marcados_troca_senha'], 1)

    def test_atualizar_senha_existente_redefine_senha_e_forca_troca(self):
        User = get_user_model()
        usuario = User.objects.create_user(
            username='existente',
            email='existente@i9tmg.com.br',
            password='SenhaAtual!2026',
            must_change_password=False,
        )
        importador = self._importador(atualizar_senha_existentes=True)

        senha_redefinida = importador._aplicar_politica_usuario_existente(usuario)

        usuario.refresh_from_db()
        self.assertTrue(senha_redefinida)
        self.assertTrue(usuario.check_password('tmg@2026'))
        self.assertTrue(usuario.must_change_password)
        self.assertEqual(importador.relatorio.contadores['usuarios_existentes_marcados_troca_senha'], 1)
        self.assertEqual(importador.relatorio.contadores['senhas_existentes_redefinidas'], 1)

    def test_gerson_respeita_gestor_da_planilha(self):
        importador = self._importador()

        gestor = importador._gestor_com_override(self._linha())

        self.assertEqual(gestor, 'DANILO')
        self.assertEqual(importador.relatorio.overrides, [])
