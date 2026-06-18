from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rh.forms import SolicitacaoVagaForm
from rh.models import AvaliacaoDesempenho, PesquisaDemissional, Vaga
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
