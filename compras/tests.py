from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command, CommandParser
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from compras.models import ComprasSyncLog, PmsCustoTarefa, PmsEdt, PmsProjeto, PmsTarefa
from compras.management.commands.sync_pms_dashboard import Command as SyncPmsDashboardCommand
from compras.selectors import PmsDashboardSelector
from compras.services.etl_service import ComprasETLService
from compras.services.pms_etl_service import ComprasPmsETLService
from compras.services.pms_hierarchy import (
    calcular_indicadores_empenho,
    consolidar_custos_por_edt,
)
from compras.tasks import LOCK_SYNC_COMPRAS, LOCK_SYNC_COMPRAS_PMS

import pandas as pd


class PmsHierarchyTests(TestCase):
    def test_consolida_custos_da_edt_com_descendentes(self):
        edts = [
            {'edt': '01', 'edt_pai': ''},
            {'edt': '01.01', 'edt_pai': '01'},
            {'edt': '01.01.01', 'edt_pai': '01.01'},
        ]
        tarefas = [
            {'tarefa': 'T1', 'edt': '01'},
            {'tarefa': 'T2', 'edt': '01.01'},
            {'tarefa': 'T3', 'edt': '01.01.01'},
        ]
        custos = [
            {'tarefa': 'T1', 'custo_previsto': Decimal('100.00'), 'custo_realizado': Decimal('10.00')},
            {'tarefa': 'T2', 'custo_previsto': Decimal('200.00'), 'custo_realizado': Decimal('20.00')},
            {'tarefa': 'T3', 'custo_previsto': Decimal('300.00'), 'custo_realizado': Decimal('30.00')},
        ]

        resultado = consolidar_custos_por_edt(edts, tarefas, custos)

        self.assertEqual(resultado['01']['custo_previsto'], Decimal('600.00'))
        self.assertEqual(resultado['01']['custo_realizado'], Decimal('60.00'))
        self.assertEqual(resultado['01']['custo'], Decimal('60.00'))
        self.assertEqual(resultado['01']['empenhado'], Decimal('0'))
        self.assertEqual(resultado['01']['saldo_empenho'], Decimal('-60.00'))
        self.assertEqual(resultado['01']['custo_sem_empenho'], Decimal('60.00'))
        self.assertEqual(resultado['01']['situacao_financeira'], 'custo_sem_empenho')
        self.assertEqual(resultado['01']['tarefas_count'], 3)
        self.assertEqual(resultado['01.01']['custo_previsto'], Decimal('500.00'))
        self.assertEqual(resultado['01.01.01']['custo_previsto'], Decimal('300.00'))

    def test_calcula_indicadores_de_custo_acima_do_empenho(self):
        resultado = calcular_indicadores_empenho(
            custo=Decimal('250.00'),
            empenhado=Decimal('100.00'),
        )

        self.assertEqual(resultado['saldo_empenho'], Decimal('-150.00'))
        self.assertEqual(resultado['percentual_custo_empenhado'], Decimal('250.0'))
        self.assertEqual(resultado['situacao_financeira'], 'custo_acima_empenho')


class PmsDashboardSelectorTests(TestCase):
    def setUp(self):
        PmsProjeto.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            descricao='D01_SISTEMA DE DESCARGA 300T/H',
        )
        PmsEdt.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            edt='01',
            descricao='Sistema',
            nivel=1,
        )
        PmsEdt.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            edt='01.01',
            edt_pai='01',
            descricao='Moega',
            nivel=2,
        )
        PmsTarefa.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            tarefa='01.01.01.01',
            edt='01.01',
            descricao='Materia-prima',
            quantidade=Decimal('10.00'),
            custo_previsto=Decimal('1000.00'),
        )
        PmsCustoTarefa.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            edt='01.01',
            tarefa='01.01.01.01',
            custo_previsto=Decimal('1000.00'),
            custo_realizado=Decimal('250.00'),
            custo_empenhado=Decimal('100.00'),
            saldo_previsto_realizado=Decimal('750.00'),
            variacao_percentual=Decimal('25.00'),
        )

    def test_contexto_retorna_kpis_e_linhas_hierarquicas(self):
        context = PmsDashboardSelector.get_context({
            'projeto': 'JP010125',
        })

        self.assertEqual(context['projeto_atual'].projeto, 'JP010125')
        self.assertEqual(context['kpis']['custo_previsto'], Decimal('1000.00'))
        self.assertEqual(context['kpis']['custo_realizado'], Decimal('250.00'))
        self.assertEqual(context['kpis']['custo'], Decimal('250.00'))
        self.assertEqual(context['kpis']['empenhado'], Decimal('100.00'))
        self.assertEqual(context['kpis']['saldo_empenho'], Decimal('-150.00'))
        self.assertEqual(context['kpis']['percentual_custo_empenhado'], Decimal('250.0'))
        self.assertEqual(context['kpis']['situacao_financeira'], 'custo_acima_empenho')
        self.assertEqual(len(context['linhas_hierarquia']), 3)

        linha_edt_pai = context['linhas_hierarquia'][0]
        self.assertEqual(linha_edt_pai['tipo'], 'edt')
        self.assertEqual(linha_edt_pai['custo_previsto'], Decimal('1000.00'))
        self.assertEqual(linha_edt_pai['custo'], Decimal('250.00'))
        self.assertEqual(context['grafico_edts']['data'], [250.0, 250.0])
        self.assertEqual(context['grafico_tarefas']['custo'], [250.0])

    def test_contexto_ignora_revisao_informada_no_filtro(self):
        PmsProjeto.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0001',
            descricao='Revisao antiga',
        )

        context = PmsDashboardSelector.get_context({
            'projeto': 'JP010125',
            'revisao': '0001',
        })

        self.assertEqual(context['projeto_atual'].revisao, '0002')
        self.assertNotIn('revisao', context['filtros'])
        self.assertEqual(context['kpis']['custo'], Decimal('250.00'))

    def test_contexto_carteira_retorna_ranking_sem_carregar_arvore(self):
        context = PmsDashboardSelector.get_context()

        self.assertTrue(context['modo_carteira'])
        self.assertIsNone(context['projeto_atual'])
        self.assertEqual(context['linhas_hierarquia'], [])
        self.assertEqual(context['kpis']['custo'], Decimal('250.00'))
        self.assertEqual(context['grafico_projetos']['labels'], ['JP010125'])
        self.assertEqual(context['grafico_projetos']['custo'], [250.0])
        self.assertEqual(context['grafico_projetos']['empenhado'], [100.0])

    def test_paginacao_inclui_ancestrais_da_linha_paginada(self):
        linhas = [
            {'tipo': 'edt', 'codigo': '01', 'parent_chain': ''},
            {'tipo': 'edt', 'codigo': '01.01', 'parent_chain': '01'},
        ]
        linhas.extend([
            {
                'tipo': 'tarefa',
                'codigo': f'T{indice:03d}',
                'parent_chain': '01|01.01',
            }
            for indice in range(1, 100)
        ])

        pagina = PmsDashboardSelector._paginar_linhas(linhas, 2)

        self.assertEqual(pagina.number, 2)
        self.assertEqual(pagina.paginator.count, 101)
        self.assertEqual(
            [linha['codigo'] for linha in pagina.object_list],
            ['01', '01.01', 'T099'],
        )


class PmsDashboardViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='compras_pms', password='senha')
        grupo, _ = Group.objects.get_or_create(name='Compras')
        self.user.groups.add(grupo)

        PmsProjeto.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            descricao='Projeto PMS',
        )

    def test_dashboard_pms_renderiza_para_usuario_compras(self):
        self.client.force_login(self.user)

        response = self.client.get('/compras/dashboard/', HTTP_HOST='localhost')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard Financeiro PMS')
        self.assertContains(response, 'Projeto &gt; EDT/WBS &gt; Tarefa')
        self.assertContains(response, 'Top 10 Projetos por Custo')
        self.assertContains(response, 'Selecione um projeto para consultar a estrutura tree')
        self.assertNotContains(response, 'Revisão')

    def test_dashboard_identifica_custo_sem_empenho(self):
        PmsEdt.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            edt='01',
            descricao='EDT sem orcamento',
            nivel=1,
        )
        PmsTarefa.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            tarefa='T1',
            edt='01',
            descricao='Tarefa realizada',
            custo_previsto=Decimal('0'),
        )
        PmsCustoTarefa.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            edt='01',
            tarefa='T1',
            custo_previsto=Decimal('0'),
            custo_realizado=Decimal('100'),
            custo_empenhado=Decimal('0'),
            saldo_previsto_realizado=Decimal('-100'),
            variacao_percentual=Decimal('0'),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            '/compras/dashboard/',
            {'projeto': 'JP010125'},
            HTTP_HOST='localhost',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Custo sem empenho', count=2)
        self.assertNotContains(response, 'Sem orçamento')

    def test_dashboard_pms_respeita_pagina_solicitada(self):
        PmsEdt.objects.bulk_create([
            PmsEdt(
                filial='01',
                projeto='JP010125',
                revisao='0002',
                edt=f'{indice:03d}',
                descricao=f'EDT {indice:03d}',
                nivel=1,
            )
            for indice in range(1, 102)
        ])
        self.client.force_login(self.user)

        response = self.client.get(
            '/compras/dashboard/',
            {
                'projeto': 'JP010125',
                'page': 2,
            },
            HTTP_HOST='localhost',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['linhas_hierarquia_page'].number, 2)
        self.assertEqual(len(response.context['linhas_hierarquia']), 1)
        self.assertEqual(response.context['linhas_hierarquia'][0]['codigo'], '101')
        self.assertContains(response, 'Linhas 101 a 101 de 101')


class ComprasSyncAuthorizationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        grupo, _ = Group.objects.get_or_create(name='Compras')
        self.user = User.objects.create_user(
            username='compras_sync',
            email='compras_sync@example.com',
            password='senha',
        )
        self.user.groups.add(grupo)
        self.staff_user = User.objects.create_user(
            username='compras_sync_staff',
            email='compras_sync_staff@example.com',
            password='senha',
            is_staff=True,
        )
        self.staff_user.groups.add(grupo)
        cache.delete(LOCK_SYNC_COMPRAS)
        cache.delete(LOCK_SYNC_COMPRAS_PMS)

    def tearDown(self):
        cache.delete(LOCK_SYNC_COMPRAS)
        cache.delete(LOCK_SYNC_COMPRAS_PMS)

    @patch('compras.views.task_sincronizar_pms_protheus.delay')
    @patch('compras.views.task_sincronizar_protheus.delay')
    def test_usuario_comum_nao_dispara_sincronizacoes(
        self,
        legacy_delay_mock,
        pms_delay_mock,
    ):
        self.client.force_login(self.user)

        response_pms = self.client.post(
            '/compras/atualizar-pms/',
            HTTP_HOST='localhost',
        )
        response_legacy = self.client.post(
            '/compras/atualizar-dados/',
            HTTP_HOST='localhost',
        )

        self.assertEqual(response_pms.status_code, 403)
        self.assertEqual(response_legacy.status_code, 403)
        self.assertEqual(response_pms.json()['status'], 'forbidden')
        self.assertEqual(response_legacy.json()['status'], 'forbidden')
        pms_delay_mock.assert_not_called()
        legacy_delay_mock.assert_not_called()

    @patch('compras.views.task_sincronizar_pms_protheus.delay')
    @patch('compras.views.task_sincronizar_protheus.delay')
    def test_usuario_staff_dispara_sincronizacoes(
        self,
        legacy_delay_mock,
        pms_delay_mock,
    ):
        legacy_delay_mock.return_value.id = 'legacy-task-id'
        pms_delay_mock.return_value.id = 'pms-task-id'
        self.client.force_login(self.staff_user)

        response_pms = self.client.post(
            '/compras/atualizar-pms/',
            HTTP_HOST='localhost',
        )
        response_legacy = self.client.post(
            '/compras/atualizar-dados/',
            HTTP_HOST='localhost',
        )

        self.assertEqual(response_pms.status_code, 200)
        self.assertEqual(response_legacy.status_code, 200)
        self.assertEqual(response_pms.json()['status'], 'processing')
        self.assertEqual(response_legacy.json()['status'], 'processing')
        pms_delay_mock.assert_called_once_with()
        legacy_delay_mock.assert_called_once_with()

    @patch('compras.views.task_sincronizar_pms_protheus.delay')
    @patch('compras.views.task_sincronizar_protheus.delay')
    def test_endpoints_recusam_execucao_com_locks_existentes(
        self,
        legacy_delay_mock,
        pms_delay_mock,
    ):
        cache.set(LOCK_SYNC_COMPRAS, True, timeout=60)
        cache.set(LOCK_SYNC_COMPRAS_PMS, True, timeout=60)
        self.client.force_login(self.staff_user)

        response_pms = self.client.post(
            '/compras/atualizar-pms/',
            HTTP_HOST='localhost',
        )
        response_legacy = self.client.post(
            '/compras/atualizar-dados/',
            HTTP_HOST='localhost',
        )

        self.assertEqual(response_pms.json()['status'], 'locked')
        self.assertEqual(response_legacy.json()['status'], 'locked')
        pms_delay_mock.assert_not_called()
        legacy_delay_mock.assert_not_called()

    @patch('compras.views.logger.exception')
    @patch(
        'compras.views.task_sincronizar_pms_protheus.delay',
        side_effect=RuntimeError('broker indisponivel'),
    )
    @patch(
        'compras.views.task_sincronizar_protheus.delay',
        side_effect=RuntimeError('broker indisponivel'),
    )
    def test_endpoints_liberam_lock_quando_broker_falha(
        self,
        legacy_delay_mock,
        pms_delay_mock,
        logger_mock,
    ):
        self.client.force_login(self.staff_user)

        response_pms = self.client.post(
            '/compras/atualizar-pms/',
            HTTP_HOST='localhost',
        )
        response_legacy = self.client.post(
            '/compras/atualizar-dados/',
            HTTP_HOST='localhost',
        )

        self.assertEqual(response_pms.status_code, 503)
        self.assertEqual(response_legacy.status_code, 503)
        self.assertEqual(response_pms.json()['status'], 'error')
        self.assertEqual(response_legacy.json()['status'], 'error')
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS_PMS))
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS))
        pms_delay_mock.assert_called_once_with()
        legacy_delay_mock.assert_called_once_with()
        self.assertEqual(logger_mock.call_count, 2)

    def test_botoes_de_sincronizacao_ficam_ocultos_para_usuario_comum(self):
        self.client.force_login(self.user)
        telas = [
            ('/compras/dashboard/', '/compras/atualizar-pms/'),
            ('/compras/operacional/', '/compras/atualizar-dados/'),
            ('/compras/avaliacoes/pendentes/', '/compras/atualizar-dados/'),
        ]

        for tela, endpoint_sync in telas:
            with self.subTest(tela=tela):
                response = self.client.get(tela, HTTP_HOST='localhost')

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(
                    response,
                    f'data-url="{endpoint_sync}"',
                )

    def test_botoes_de_sincronizacao_ficam_visiveis_para_staff(self):
        self.client.force_login(self.staff_user)
        telas = [
            ('/compras/dashboard/', '/compras/atualizar-pms/'),
            ('/compras/operacional/', '/compras/atualizar-dados/'),
            ('/compras/avaliacoes/pendentes/', '/compras/atualizar-dados/'),
        ]

        for tela, endpoint_sync in telas:
            with self.subTest(tela=tela):
                response = self.client.get(tela, HTTP_HOST='localhost')

                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    f'data-url="{endpoint_sync}"',
                )


class PmsModelConstraintTests(TestCase):
    def test_projeto_nao_permite_chave_natural_duplicada(self):
        PmsProjeto.objects.create(filial='01', projeto='JP010125', revisao='0002')

        with self.assertRaises(IntegrityError):
            PmsProjeto.objects.create(filial='01', projeto='JP010125', revisao='0002')


class ComprasLegacyETLServiceTests(TestCase):
    @patch.object(ComprasETLService, '_salvar_no_banco')
    @patch.object(ComprasETLService, '_exportar_relatorio_operacional')
    @patch.object(ComprasETLService, '_processar_operacional')
    def test_transformar_e_salvar_executa_apenas_fluxo_operacional(
        self,
        processar_operacional_mock,
        exportar_mock,
        salvar_mock,
    ):
        dados_limpos = {'origem': 'teste'}
        dataframe_operacional = pd.DataFrame([{'Num_SC': '000001'}])
        processar_operacional_mock.return_value = dataframe_operacional

        resultado = ComprasETLService.transformar_e_salvar(dados_limpos)

        self.assertTrue(resultado)
        self.assertFalse(hasattr(ComprasETLService, '_processar_dw'))
        processar_operacional_mock.assert_called_once_with(dados_limpos)
        exportar_mock.assert_called_once_with(dataframe_operacional)
        salvar_mock.assert_called_once_with(dataframe_operacional)


class ComprasPmsETLServiceTests(TestCase):
    def test_validar_schema_falha_com_colunas_obrigatorias_ausentes(self):
        dados = {
            'af8': pd.DataFrame([{'X': '1'}]),
            'afc': pd.DataFrame([{'X': '1'}]),
            'af9': pd.DataFrame([{'X': '1'}]),
        }

        with self.assertRaisesMessage(ValueError, 'Arquivo AF8 sem colunas obrigatorias'):
            ComprasPmsETLService._validar_schema(dados)

    def test_validar_schema_aceita_colunas_minimas(self):
        dados = {
            'af8': pd.DataFrame([{
                'AF8_FILIAL': '01',
                'AF8_PROJET': 'JP010125',
                'AF8_REVISA': '0002',
            }]),
            'afc': pd.DataFrame([{
                'AFC_FILIAL': '01',
                'AFC_PROJET': 'JP010125',
                'AFC_REVISA': '0002',
                'AFC_EDT': '01',
            }]),
            'af9': pd.DataFrame([{
                'AF9_FILIAL': '01',
                'AF9_PROJET': 'JP010125',
                'AF9_REVISA': '0002',
                'AF9_TAREFA': '01.01.01.01',
                'AF9_EDTPAI': '01',
                'AF9_CUSTO': '1000',
            }]),
            'afg': pd.DataFrame([{
                'AFG_FILIAL': '01',
                'AFG_PROJET': 'JP010125',
                'AFG_REVISA': '0002',
                'AFG_TAREFA': '01.01.01.01',
                'AFG_NUMSC': '000001',
                'AFG_ITEMSC': '0001',
                'AFG_QUANT': '1',
            }]),
            'sc7': pd.DataFrame([{
                'C7_FILIAL': '01',
                'C7_NUMSC': '000001',
                'C7_ITEMSC': '0001',
                'C7_NUM': '000001',
                'C7_ITEM': '0001',
                'C7_TOTAL': '1000',
            }]),
            'sd1': pd.DataFrame([{
                'D1_FILIAL': '01',
                'D1_PEDIDO': '000001',
                'D1_ITEMPC': '0001',
                'D1_TOTAL': '500',
            }]),
        }

        ComprasPmsETLService._validar_schema(dados)

    def test_montar_custos_rateia_empenhado_e_realizado_por_tarefa(self):
        tarefas = pd.DataFrame([
            {
                'AF9_FILIAL': '01',
                'AF9_PROJET': 'JP010125',
                'AF9_REVISA': '0002',
                'AF9_TAREFA': 'T1',
                'AF9_EDTPAI': '01',
                'AF9_CUSTO': '1000',
            },
            {
                'AF9_FILIAL': '01',
                'AF9_PROJET': 'JP010125',
                'AF9_REVISA': '0002',
                'AF9_TAREFA': 'T2',
                'AF9_EDTPAI': '01',
                'AF9_CUSTO': '1000',
            },
        ])
        mapeamentos = pd.DataFrame([
            {
                'AFG_FILIAL': '01',
                'AFG_PROJET': 'JP010125',
                'AFG_REVISA': '0002',
                'AFG_TAREFA': 'T1',
                'AFG_NUMSC': 'SC1',
                'AFG_ITEMSC': '01',
                'AFG_QUANT': '1',
            },
            {
                'AFG_FILIAL': '01',
                'AFG_PROJET': 'JP010125',
                'AFG_REVISA': '0002',
                'AFG_TAREFA': 'T2',
                'AFG_NUMSC': 'SC1',
                'AFG_ITEMSC': '01',
                'AFG_QUANT': '3',
            },
        ])
        pedidos = pd.DataFrame([
            {
                'C7_FILIAL': '01',
                'C7_NUMSC': 'SC1',
                'C7_ITEMSC': '01',
                'C7_NUM': 'PC1',
                'C7_ITEM': '01',
                'C7_TOTAL': '400',
            },
            {
                'C7_FILIAL': '01',
                'C7_NUMSC': 'SC1',
                'C7_ITEMSC': '01',
                'C7_NUM': 'PC1',
                'C7_ITEM': '01',
                'C7_TOTAL': '400',
            },
        ])
        recebimentos = pd.DataFrame([
            {
                'D1_FILIAL': '01',
                'D1_PEDIDO': 'PC1',
                'D1_ITEMPC': '01',
                'D1_TOTAL': '80',
            },
            {
                'D1_FILIAL': '01',
                'D1_PEDIDO': 'PC1',
                'D1_ITEMPC': '01',
                'D1_TOTAL': '120',
            },
        ])

        custos = ComprasPmsETLService._montar_custos(
            df_tarefas=tarefas,
            df_produtos=pd.DataFrame(),
            df_despesas=pd.DataFrame(),
            df_mapeamentos=mapeamentos,
            df_pedidos=pedidos,
            df_recebimentos=recebimentos,
        )
        custos_por_tarefa = {custo.tarefa: custo for custo in custos}

        self.assertEqual(custos_por_tarefa['T1'].custo_empenhado, Decimal('100'))
        self.assertEqual(custos_por_tarefa['T2'].custo_empenhado, Decimal('300'))
        self.assertEqual(custos_por_tarefa['T1'].custo_realizado, Decimal('50'))
        self.assertEqual(custos_por_tarefa['T2'].custo_realizado, Decimal('150'))
        self.assertEqual(
            sum((custo.custo_empenhado for custo in custos), Decimal('0')),
            Decimal('400'),
        )
        self.assertEqual(
            sum((custo.custo_realizado for custo in custos), Decimal('0')),
            Decimal('200'),
        )

    def test_rateio_rejeita_solicitacao_sem_quantidade(self):
        mapeamentos = pd.DataFrame([{
            'AFG_FILIAL': '01',
            'AFG_PROJET': 'JP010125',
            'AFG_REVISA': '0002',
            'AFG_TAREFA': 'T1',
            'AFG_NUMSC': 'SC1',
            'AFG_ITEMSC': '01',
            'AFG_QUANT': '0',
        }])

        with self.assertRaisesMessage(
            ValueError,
            'Distribuicao PMS sem quantidade para a solicitacao',
        ):
            ComprasPmsETLService._rateios_por_solicitacao(mapeamentos)

    def test_transformar_e_salvar_remove_dados_obsoletos(self):
        PmsProjeto.objects.create(
            filial='01',
            projeto='ANTIGO',
            revisao='0001',
        )
        PmsEdt.objects.create(
            filial='01',
            projeto='ANTIGO',
            revisao='0001',
            edt='01',
        )
        PmsTarefa.objects.create(
            filial='01',
            projeto='ANTIGO',
            revisao='0001',
            tarefa='T-ANTIGA',
            edt='01',
        )
        PmsCustoTarefa.objects.create(
            filial='01',
            projeto='ANTIGO',
            revisao='0001',
            tarefa='T-ANTIGA',
            edt='01',
        )
        dados = {
            'af8': pd.DataFrame([{
                'AF8_FILIAL': '01',
                'AF8_PROJET': 'NOVO',
                'AF8_REVISA': '0002',
            }]),
            'afc': pd.DataFrame([{
                'AFC_FILIAL': '01',
                'AFC_PROJET': 'NOVO',
                'AFC_REVISA': '0002',
                'AFC_EDT': '01',
            }]),
            'af9': pd.DataFrame([{
                'AF9_FILIAL': '01',
                'AF9_PROJET': 'NOVO',
                'AF9_REVISA': '0002',
                'AF9_TAREFA': 'T1',
                'AF9_EDTPAI': '01',
                'AF9_CUSTO': '100',
            }]),
            'afa': pd.DataFrame(),
            'afb': pd.DataFrame(),
            'afg': pd.DataFrame([{
                'AFG_FILIAL': '01',
                'AFG_PROJET': 'NOVO',
                'AFG_REVISA': '0002',
                'AFG_TAREFA': 'T1',
                'AFG_NUMSC': 'SC1',
                'AFG_ITEMSC': '01',
                'AFG_QUANT': '1',
            }]),
            'sc7': pd.DataFrame([{
                'C7_FILIAL': '01',
                'C7_NUMSC': 'SC1',
                'C7_ITEMSC': '01',
                'C7_NUM': 'PC1',
                'C7_ITEM': '01',
                'C7_TOTAL': '40',
            }]),
            'sd1': pd.DataFrame([{
                'D1_FILIAL': '01',
                'D1_PEDIDO': 'PC1',
                'D1_ITEMPC': '01',
                'D1_TOTAL': '20',
            }]),
        }

        resultado = ComprasPmsETLService.transformar_e_salvar(dados)

        self.assertTrue(resultado)
        self.assertFalse(PmsProjeto.objects.filter(projeto='ANTIGO').exists())
        self.assertFalse(PmsEdt.objects.filter(projeto='ANTIGO').exists())
        self.assertFalse(PmsTarefa.objects.filter(projeto='ANTIGO').exists())
        self.assertFalse(PmsCustoTarefa.objects.filter(projeto='ANTIGO').exists())
        self.assertEqual(PmsProjeto.objects.get().projeto, 'NOVO')
        self.assertEqual(PmsEdt.objects.get().projeto, 'NOVO')
        self.assertEqual(PmsTarefa.objects.get().tarefa, 'T1')
        custo = PmsCustoTarefa.objects.get()
        self.assertEqual(custo.custo_previsto, Decimal('100'))
        self.assertEqual(custo.custo_empenhado, Decimal('40'))
        self.assertEqual(custo.custo_realizado, Decimal('20'))
        self.assertEqual(ComprasSyncLog.objects.get().status, ComprasSyncLog.STATUS_SUCESSO)

    def test_salvar_projetos_atualiza_por_chave_natural(self):
        PmsProjeto.objects.create(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            descricao='Descricao antiga',
        )
        projeto_atualizado = PmsProjeto(
            filial='01',
            projeto='JP010125',
            revisao='0002',
            descricao='Descricao atualizada',
        )

        ComprasPmsETLService._salvar_projetos([projeto_atualizado])

        self.assertEqual(PmsProjeto.objects.count(), 1)
        self.assertEqual(
            PmsProjeto.objects.get(filial='01', projeto='JP010125', revisao='0002').descricao,
            'Descricao atualizada',
        )


class SyncPmsDashboardCommandTests(TestCase):
    def setUp(self):
        cache.delete(LOCK_SYNC_COMPRAS_PMS)

    def tearDown(self):
        cache.delete(LOCK_SYNC_COMPRAS_PMS)

    def test_command_registra_opcao_dry_run(self):
        command = SyncPmsDashboardCommand()
        parser = CommandParser(prog='sync_pms_dashboard')
        command.add_arguments(parser)

        options = parser.parse_args(['--dry-run'])

        self.assertTrue(options.dry_run)

    @patch(
        'compras.management.commands.sync_pms_dashboard.'
        'dowload_files_sftp'
    )
    @patch.object(ComprasPmsETLService, '_ler_e_limpar_arquivos')
    def test_dry_run_exibe_totais_financeiros(
        self,
        ler_arquivos_mock,
        download_mock,
    ):
        ler_arquivos_mock.return_value = {
            'af8': pd.DataFrame([{
                'AF8_FILIAL': '01',
                'AF8_PROJET': 'JP010125',
                'AF8_REVISA': '0002',
            }]),
            'afc': pd.DataFrame([{
                'AFC_FILIAL': '01',
                'AFC_PROJET': 'JP010125',
                'AFC_REVISA': '0002',
                'AFC_EDT': '01',
            }]),
            'af9': pd.DataFrame([{
                'AF9_FILIAL': '01',
                'AF9_PROJET': 'JP010125',
                'AF9_REVISA': '0002',
                'AF9_TAREFA': 'T1',
                'AF9_EDTPAI': '01',
                'AF9_CUSTO': '1000',
            }]),
            'afa': pd.DataFrame(),
            'afb': pd.DataFrame(),
            'afg': pd.DataFrame([{
                'AFG_FILIAL': '01',
                'AFG_PROJET': 'JP010125',
                'AFG_REVISA': '0002',
                'AFG_TAREFA': 'T1',
                'AFG_NUMSC': 'SC1',
                'AFG_ITEMSC': '01',
                'AFG_QUANT': '1',
            }]),
            'sc7': pd.DataFrame([{
                'C7_FILIAL': '01',
                'C7_NUMSC': 'SC1',
                'C7_ITEMSC': '01',
                'C7_NUM': 'PC1',
                'C7_ITEM': '01',
                'C7_TOTAL': '400',
            }]),
            'sd1': pd.DataFrame([{
                'D1_FILIAL': '01',
                'D1_PEDIDO': 'PC1',
                'D1_ITEMPC': '01',
                'D1_TOTAL': '200',
            }]),
        }
        stdout = StringIO()

        call_command('sync_pms_dashboard', '--dry-run', stdout=stdout)

        output = stdout.getvalue()
        download_mock.assert_called_once()
        ler_arquivos_mock.assert_called_once()
        self.assertIn('Custo previsto: 1000.00', output)
        self.assertIn('Custo empenhado: 400.00', output)
        self.assertIn('Custo realizado: 200.00', output)
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS_PMS))

    @patch(
        'compras.management.commands.sync_pms_dashboard.'
        'ComprasPmsETLService.executar'
    )
    def test_command_executa_service_e_libera_lock(self, executar_mock):
        stdout = StringIO()

        call_command('sync_pms_dashboard', stdout=stdout)

        executar_mock.assert_called_once_with()
        self.assertIn(
            'Sincronizacao PMS de Compras concluida.',
            stdout.getvalue(),
        )
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS_PMS))

    @patch(
        'compras.management.commands.sync_pms_dashboard.'
        'ComprasPmsETLService.executar',
        side_effect=RuntimeError('falha controlada'),
    )
    def test_command_libera_lock_apos_falha(self, executar_mock):
        with self.assertRaisesMessage(
            CommandError,
            'Falha na sincronizacao PMS de Compras: falha controlada',
        ):
            call_command('sync_pms_dashboard', stdout=StringIO())

        executar_mock.assert_called_once_with()
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS_PMS))

    @patch(
        'compras.management.commands.sync_pms_dashboard.'
        'ComprasPmsETLService.executar'
    )
    def test_command_recusa_execucao_com_lock_existente(self, executar_mock):
        cache.set(LOCK_SYNC_COMPRAS_PMS, True, timeout=60)

        with self.assertRaisesMessage(
            CommandError,
            'Sincronizacao PMS de Compras ja esta em andamento.',
        ):
            call_command('sync_pms_dashboard', stdout=StringIO())

        executar_mock.assert_not_called()
        self.assertTrue(cache.get(LOCK_SYNC_COMPRAS_PMS))


class SyncComprasLegacyCommandTests(TestCase):
    def setUp(self):
        cache.delete(LOCK_SYNC_COMPRAS)

    def tearDown(self):
        cache.delete(LOCK_SYNC_COMPRAS)

    @patch(
        'compras.management.commands.sync_compras_legacy.'
        'ComprasETLService.executar'
    )
    def test_command_executa_service(self, executar_mock):
        stdout = StringIO()

        call_command('sync_compras_legacy', stdout=stdout)

        executar_mock.assert_called_once_with()
        self.assertIn(
            'Sincronizacao legada de Compras concluida.',
            stdout.getvalue(),
        )
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS))

    @patch(
        'compras.management.commands.sync_compras_legacy.'
        'ComprasETLService.executar',
        side_effect=RuntimeError('falha controlada'),
    )
    def test_command_converte_falha_em_command_error(self, executar_mock):
        with self.assertRaisesMessage(
            CommandError,
            'Falha na sincronizacao legada de Compras: falha controlada',
        ):
            call_command('sync_compras_legacy', stdout=StringIO())

        executar_mock.assert_called_once_with()
        self.assertIsNone(cache.get(LOCK_SYNC_COMPRAS))

    @patch(
        'compras.management.commands.sync_compras_legacy.'
        'ComprasETLService.executar'
    )
    def test_command_recusa_execucao_com_lock_existente(self, executar_mock):
        cache.set(LOCK_SYNC_COMPRAS, True, timeout=60)

        with self.assertRaisesMessage(
            CommandError,
            'Sincronizacao legada de Compras ja esta em andamento.',
        ):
            call_command('sync_compras_legacy', stdout=StringIO())

        executar_mock.assert_not_called()
        self.assertTrue(cache.get(LOCK_SYNC_COMPRAS))
