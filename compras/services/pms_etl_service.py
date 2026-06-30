import logging
import os
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction
from django.utils import timezone

from compras.models import ComprasSyncLog, PmsCustoTarefa, PmsEdt, PmsProjeto, PmsTarefa
from core.services.protheus_etl import ProtheusBaseETL


logger = logging.getLogger(__name__)
ZERO = Decimal('0')


class ComprasPmsETLService(ProtheusBaseETL):
    ARQUIVOS_PADRAO = [
        'af80101.sdb',
        'afc0101.sdb',
        'af90101.sdb',
        'afa0101.sdb',
        'afb0101.sdb',
        'afg0101.sdb',
        'sc70101.sdb',
        'sd10101.sdb',
    ]
    ARQUIVOS_ALVO = [
        arquivo.strip()
        for arquivo in os.getenv('COMPRAS_PMS_ARQUIVOS', ','.join(ARQUIVOS_PADRAO)).split(',')
        if arquivo.strip()
    ]

    JOB_NAME = 'compras_pms'

    COLUNAS_OBRIGATORIAS = {
        'af8': ['AF8_FILIAL', 'AF8_PROJET', 'AF8_REVISA'],
        'afc': ['AFC_FILIAL', 'AFC_PROJET', 'AFC_REVISA', 'AFC_EDT'],
        'af9': ['AF9_FILIAL', 'AF9_PROJET', 'AF9_REVISA', 'AF9_TAREFA', 'AF9_EDTPAI', 'AF9_CUSTO'],
        'afg': [
            'AFG_FILIAL',
            'AFG_PROJET',
            'AFG_REVISA',
            'AFG_TAREFA',
            'AFG_NUMSC',
            'AFG_ITEMSC',
            'AFG_QUANT',
        ],
        'sc7': [
            'C7_FILIAL',
            'C7_NUMSC',
            'C7_ITEMSC',
            'C7_NUM',
            'C7_ITEM',
            'C7_TOTAL',
        ],
        'sd1': [
            'D1_FILIAL',
            'D1_PEDIDO',
            'D1_ITEMPC',
            'D1_TOTAL',
        ],
    }

    @classmethod
    def transformar_e_salvar(cls, dados_limpos):
        sync_log = ComprasSyncLog.objects.create(
            nome=cls.JOB_NAME,
            status=ComprasSyncLog.STATUS_PROCESSANDO,
            arquivos_processados=cls.ARQUIVOS_ALVO,
        )

        try:
            cls._validar_schema(dados_limpos)

            projetos = cls._montar_projetos(dados_limpos.get('af8', pd.DataFrame()))
            edts = cls._montar_edts(dados_limpos.get('afc', pd.DataFrame()))
            tarefas = cls._montar_tarefas(dados_limpos.get('af9', pd.DataFrame()))
            custos = cls._montar_custos(
                df_tarefas=dados_limpos.get('af9', pd.DataFrame()),
                df_produtos=dados_limpos.get('afa', pd.DataFrame()),
                df_despesas=dados_limpos.get('afb', pd.DataFrame()),
                df_mapeamentos=dados_limpos.get('afg', pd.DataFrame()),
                df_pedidos=dados_limpos.get('sc7', pd.DataFrame()),
                df_recebimentos=dados_limpos.get('sd1', pd.DataFrame()),
            )

            linhas_lidas = sum(len(df) for df in dados_limpos.values())
            linhas_gravadas = len(projetos) + len(edts) + len(tarefas) + len(custos)

            with transaction.atomic():
                cls._limpar_dados_materializados()
                cls._salvar_projetos(projetos)
                cls._salvar_edts(edts)
                cls._salvar_tarefas(tarefas)
                cls._salvar_custos(custos)

                sync_log.status = ComprasSyncLog.STATUS_SUCESSO
                sync_log.finalizado_em = timezone.now()
                sync_log.linhas_lidas = linhas_lidas
                sync_log.linhas_gravadas = linhas_gravadas
                sync_log.mensagem = 'Sincronizacao PMS concluida.'
                sync_log.save(update_fields=[
                    'status',
                    'finalizado_em',
                    'linhas_lidas',
                    'linhas_gravadas',
                    'mensagem',
                ])

            logger.info("[COMPRAS PMS] Sincronizacao concluida: %s linhas gravadas.", linhas_gravadas)
            return True
        except Exception as exc:
            sync_log.status = ComprasSyncLog.STATUS_ERRO
            sync_log.finalizado_em = timezone.now()
            sync_log.erro = str(exc)
            sync_log.save(update_fields=['status', 'finalizado_em', 'erro'])
            logger.exception("[COMPRAS PMS] Erro ao sincronizar dados PMS.")
            raise

    @staticmethod
    def _limpar_dados_materializados():
        PmsCustoTarefa.objects.all().delete()
        PmsTarefa.objects.all().delete()
        PmsEdt.objects.all().delete()
        PmsProjeto.objects.all().delete()

    @classmethod
    def _montar_projetos(cls, df):
        if df.empty:
            return []

        registros = []
        colunas_chave = cls._colunas_existentes(df, ['AF8_FILIAL', 'AF8_PROJET', 'AF8_REVISA'])
        if colunas_chave:
            df = df.drop_duplicates(subset=colunas_chave)

        for _, row in df.iterrows():
            filial = cls._texto(row.get('AF8_FILIAL'))
            projeto = cls._texto(row.get('AF8_PROJET'))
            revisao = cls._texto(row.get('AF8_REVISA'))
            if not filial or not projeto or not revisao:
                continue

            registros.append(PmsProjeto(
                filial=filial,
                projeto=projeto,
                revisao=revisao,
                descricao=cls._texto(row.get('AF8_DESCRI')),
                data_base=cls._data(row.get('AF8_DATA')),
                calendario=cls._texto(row.get('AF8_CALEND')),
                mascara=cls._texto(row.get('AF8_MASCAR')),
                delimitador=cls._texto(row.get('AF8_DELIM')),
            ))

        return cls._deduplicar(registros, lambda item: (item.filial, item.projeto, item.revisao))

    @classmethod
    def _montar_edts(cls, df):
        if df.empty:
            return []

        registros = []
        for _, row in df.iterrows():
            filial = cls._texto(row.get('AFC_FILIAL'))
            projeto = cls._texto(row.get('AFC_PROJET'))
            revisao = cls._texto(row.get('AFC_REVISA'))
            edt = cls._texto(row.get('AFC_EDT'))
            if not filial or not projeto or not revisao or not edt:
                continue

            registros.append(PmsEdt(
                filial=filial,
                projeto=projeto,
                revisao=revisao,
                edt=edt,
                edt_pai=cls._texto(row.get('AFC_EDTPAI')),
                descricao=cls._texto(row.get('AFC_DESCRI')),
                nivel=cls._inteiro(row.get('AFC_NIVEL')),
                ordem=cls._texto(row.get('AFC_ORDEM')),
                unidade=cls._texto(row.get('AFC_UM')),
                quantidade=cls._decimal(row.get('AFC_QUANT')),
                custo_previsto=cls._decimal(row.get('AFC_CUSTO')),
            ))

        return cls._deduplicar(registros, lambda item: (item.filial, item.projeto, item.revisao, item.edt))

    @classmethod
    def _montar_tarefas(cls, df):
        if df.empty:
            return []

        registros = []
        for _, row in df.iterrows():
            filial = cls._texto(row.get('AF9_FILIAL'))
            projeto = cls._texto(row.get('AF9_PROJET'))
            revisao = cls._texto(row.get('AF9_REVISA'))
            tarefa = cls._texto(row.get('AF9_TAREFA'))
            if not filial or not projeto or not revisao or not tarefa:
                continue

            registros.append(PmsTarefa(
                filial=filial,
                projeto=projeto,
                revisao=revisao,
                tarefa=tarefa,
                edt=cls._texto(row.get('AF9_EDTPAI')),
                descricao=cls._texto(row.get('AF9_DESCRI')),
                nivel=cls._inteiro(row.get('AF9_NIVEL')),
                ordem=cls._texto(row.get('AF9_ORDEM')),
                unidade=cls._texto(row.get('AF9_UM')),
                quantidade=cls._decimal(row.get('AF9_QUANT')),
                data_inicio_prevista=cls._data(row.get('AF9_START')),
                data_fim_prevista=cls._data(row.get('AF9_FINISH')),
                custo_previsto=cls._decimal(row.get('AF9_CUSTO')),
            ))

        return cls._deduplicar(registros, lambda item: (item.filial, item.projeto, item.revisao, item.tarefa))

    @classmethod
    def _montar_custos(
        cls,
        df_tarefas,
        df_produtos,
        df_despesas,
        df_mapeamentos=None,
        df_pedidos=None,
        df_recebimentos=None,
    ):
        if df_tarefas.empty:
            return []

        produtos_por_tarefa = cls._custos_produtos_por_tarefa(df_produtos)
        despesas_por_tarefa = cls._custos_despesas_por_tarefa(df_despesas)
        empenhado_por_tarefa, realizado_por_tarefa = cls._custos_financeiros_por_tarefa(
            df_mapeamentos=df_mapeamentos if df_mapeamentos is not None else pd.DataFrame(),
            df_pedidos=df_pedidos if df_pedidos is not None else pd.DataFrame(),
            df_recebimentos=df_recebimentos if df_recebimentos is not None else pd.DataFrame(),
        )

        registros = []
        for _, row in df_tarefas.iterrows():
            filial = cls._texto(row.get('AF9_FILIAL'))
            projeto = cls._texto(row.get('AF9_PROJET'))
            revisao = cls._texto(row.get('AF9_REVISA'))
            tarefa = cls._texto(row.get('AF9_TAREFA'))
            if not filial or not projeto or not revisao or not tarefa:
                continue

            chave = (filial, projeto, revisao, tarefa)
            custo_previsto = cls._decimal(row.get('AF9_CUSTO'))
            custo_produtos = produtos_por_tarefa.get(chave, ZERO)
            custo_despesas = despesas_por_tarefa.get(chave, ZERO)
            custo_detalhado = custo_produtos + custo_despesas
            custo_realizado = realizado_por_tarefa.get(chave, ZERO)
            custo_empenhado = empenhado_por_tarefa.get(chave, ZERO)
            saldo = custo_previsto - custo_realizado
            variacao = (custo_realizado / custo_previsto) * Decimal('100') if custo_previsto else ZERO

            registros.append(PmsCustoTarefa(
                filial=filial,
                projeto=projeto,
                revisao=revisao,
                edt=cls._texto(row.get('AF9_EDTPAI')),
                tarefa=tarefa,
                custo_previsto=custo_previsto,
                custo_previsto_produtos=custo_produtos,
                custo_previsto_despesas=custo_despesas,
                custo_previsto_detalhado=custo_detalhado,
                custo_realizado=custo_realizado,
                custo_empenhado=custo_empenhado,
                saldo_previsto_realizado=saldo,
                variacao_percentual=variacao,
            ))

        return cls._deduplicar(registros, lambda item: (item.filial, item.projeto, item.revisao, item.tarefa))

    @staticmethod
    def _salvar_projetos(projetos):
        for projeto in projetos:
            PmsProjeto.objects.update_or_create(
                filial=projeto.filial,
                projeto=projeto.projeto,
                revisao=projeto.revisao,
                defaults={
                    'descricao': projeto.descricao,
                    'data_base': projeto.data_base,
                    'calendario': projeto.calendario,
                    'mascara': projeto.mascara,
                    'delimitador': projeto.delimitador,
                },
            )

    @staticmethod
    def _salvar_edts(edts):
        for edt in edts:
            PmsEdt.objects.update_or_create(
                filial=edt.filial,
                projeto=edt.projeto,
                revisao=edt.revisao,
                edt=edt.edt,
                defaults={
                    'edt_pai': edt.edt_pai,
                    'descricao': edt.descricao,
                    'nivel': edt.nivel,
                    'ordem': edt.ordem,
                    'unidade': edt.unidade,
                    'quantidade': edt.quantidade,
                    'custo_previsto': edt.custo_previsto,
                },
            )

    @staticmethod
    def _salvar_tarefas(tarefas):
        for tarefa in tarefas:
            PmsTarefa.objects.update_or_create(
                filial=tarefa.filial,
                projeto=tarefa.projeto,
                revisao=tarefa.revisao,
                tarefa=tarefa.tarefa,
                defaults={
                    'edt': tarefa.edt,
                    'descricao': tarefa.descricao,
                    'nivel': tarefa.nivel,
                    'ordem': tarefa.ordem,
                    'unidade': tarefa.unidade,
                    'quantidade': tarefa.quantidade,
                    'data_inicio_prevista': tarefa.data_inicio_prevista,
                    'data_fim_prevista': tarefa.data_fim_prevista,
                    'custo_previsto': tarefa.custo_previsto,
                },
            )

    @staticmethod
    def _salvar_custos(custos):
        for custo in custos:
            PmsCustoTarefa.objects.update_or_create(
                filial=custo.filial,
                projeto=custo.projeto,
                revisao=custo.revisao,
                tarefa=custo.tarefa,
                defaults={
                    'edt': custo.edt,
                    'custo_previsto': custo.custo_previsto,
                    'custo_previsto_produtos': custo.custo_previsto_produtos,
                    'custo_previsto_despesas': custo.custo_previsto_despesas,
                    'custo_previsto_detalhado': custo.custo_previsto_detalhado,
                    'custo_realizado': custo.custo_realizado,
                    'custo_empenhado': custo.custo_empenhado,
                    'saldo_previsto_realizado': custo.saldo_previsto_realizado,
                    'variacao_percentual': custo.variacao_percentual,
                },
            )

    @classmethod
    def _custos_financeiros_por_tarefa(
        cls,
        df_mapeamentos,
        df_pedidos,
        df_recebimentos,
    ):
        if df_mapeamentos.empty or df_pedidos.empty:
            return {}, {}

        rateios_por_sc = cls._rateios_por_solicitacao(df_mapeamentos)
        empenhado_por_tarefa = {}
        realizado_por_tarefa = {}
        rateios_por_pedido = {}
        pedidos_processados = set()

        for _, row in df_pedidos.iterrows():
            chave_sc = (
                cls._texto(row.get('C7_FILIAL')),
                cls._texto(row.get('C7_NUMSC')),
                cls._texto(row.get('C7_ITEMSC')),
            )
            chave_pedido = (
                cls._texto(row.get('C7_FILIAL')),
                cls._texto(row.get('C7_NUM')),
                cls._texto(row.get('C7_ITEM')),
            )
            rateios = rateios_por_sc.get(chave_sc)
            if not rateios or not all(chave_pedido):
                continue

            rateios_existentes = rateios_por_pedido.get(chave_pedido)
            if rateios_existentes is not None and rateios_existentes != rateios:
                raise ValueError(
                    'Pedido vinculado a mais de uma distribuicao PMS: '
                    f'{chave_pedido}'
                )
            rateios_por_pedido[chave_pedido] = rateios

            if chave_pedido in pedidos_processados:
                continue
            pedidos_processados.add(chave_pedido)

            valor_pedido = cls._decimal(row.get('C7_TOTAL'))
            for chave_tarefa, proporcao in rateios:
                empenhado_por_tarefa[chave_tarefa] = (
                    empenhado_por_tarefa.get(chave_tarefa, ZERO)
                    + (valor_pedido * proporcao)
                )

        if df_recebimentos.empty:
            return empenhado_por_tarefa, realizado_por_tarefa

        for _, row in df_recebimentos.iterrows():
            chave_pedido = (
                cls._texto(row.get('D1_FILIAL')),
                cls._texto(row.get('D1_PEDIDO')),
                cls._texto(row.get('D1_ITEMPC')),
            )
            rateios = rateios_por_pedido.get(chave_pedido)
            if not rateios:
                continue

            valor_recebido = cls._decimal(row.get('D1_TOTAL'))
            for chave_tarefa, proporcao in rateios:
                realizado_por_tarefa[chave_tarefa] = (
                    realizado_por_tarefa.get(chave_tarefa, ZERO)
                    + (valor_recebido * proporcao)
                )

        return empenhado_por_tarefa, realizado_por_tarefa

    @classmethod
    def _rateios_por_solicitacao(cls, df_mapeamentos):
        colunas = [
            'AFG_FILIAL',
            'AFG_PROJET',
            'AFG_REVISA',
            'AFG_TAREFA',
            'AFG_NUMSC',
            'AFG_ITEMSC',
            'AFG_QUANT',
        ]
        mapeamentos = {}
        for _, row in df_mapeamentos.drop_duplicates(subset=colunas).iterrows():
            chave_sc = (
                cls._texto(row.get('AFG_FILIAL')),
                cls._texto(row.get('AFG_NUMSC')),
                cls._texto(row.get('AFG_ITEMSC')),
            )
            chave_tarefa = (
                cls._texto(row.get('AFG_FILIAL')),
                cls._texto(row.get('AFG_PROJET')),
                cls._texto(row.get('AFG_REVISA')),
                cls._texto(row.get('AFG_TAREFA')),
            )
            if not all(chave_sc) or not all(chave_tarefa):
                continue

            quantidade = cls._decimal(row.get('AFG_QUANT'))
            distribuicao = mapeamentos.setdefault(chave_sc, {})
            distribuicao[chave_tarefa] = (
                distribuicao.get(chave_tarefa, ZERO) + quantidade
            )

        rateios = {}
        for chave_sc, distribuicao in mapeamentos.items():
            quantidade_total = sum(distribuicao.values(), ZERO)
            if quantidade_total <= ZERO:
                raise ValueError(
                    'Distribuicao PMS sem quantidade para a solicitacao: '
                    f'{chave_sc}'
                )
            rateios[chave_sc] = [
                (chave_tarefa, quantidade / quantidade_total)
                for chave_tarefa, quantidade in distribuicao.items()
            ]

        return rateios

    @classmethod
    def _custos_produtos_por_tarefa(cls, df):
        if df.empty:
            return {}

        custos = {}
        for _, row in df.iterrows():
            filial = cls._texto(row.get('AFA_FILIAL'))
            projeto = cls._texto(row.get('AFA_PROJET'))
            revisao = cls._texto(row.get('AFA_REVISA'))
            tarefa = cls._texto(row.get('AFA_TAREFA'))
            if not filial or not projeto or not revisao or not tarefa:
                continue

            chave = (filial, projeto, revisao, tarefa)
            quantidade = cls._decimal(row.get('AFA_QUANT'))
            custo_unitario = cls._decimal(row.get('AFA_CUSTD'))
            custos[chave] = custos.get(chave, ZERO) + (quantidade * custo_unitario)

        return custos

    @classmethod
    def _custos_despesas_por_tarefa(cls, df):
        if df.empty:
            return {}

        custos = {}
        for _, row in df.iterrows():
            filial = cls._texto(row.get('AFB_FILIAL'))
            projeto = cls._texto(row.get('AFB_PROJET'))
            revisao = cls._texto(row.get('AFB_REVISA'))
            tarefa = cls._texto(row.get('AFB_TAREFA'))
            if not filial or not projeto or not revisao or not tarefa:
                continue

            chave = (filial, projeto, revisao, tarefa)
            custos[chave] = custos.get(chave, ZERO) + cls._decimal(row.get('AFB_VALOR'))

        return custos

    @staticmethod
    def _texto(value):
        return str(value or '').strip()

    @staticmethod
    def _decimal(value):
        if value is None or value == '':
            return ZERO
        try:
            value_as_text = str(value).strip().replace(',', '.')
            if not value_as_text or value_as_text.lower() in {'nan', 'nat', 'none'}:
                return ZERO
            return Decimal(value_as_text)
        except (InvalidOperation, ValueError):
            return ZERO

    @classmethod
    def _inteiro(cls, value):
        decimal_value = cls._decimal(value)
        return int(decimal_value) if decimal_value else None

    @staticmethod
    def _data(value):
        value_as_text = str(value or '').strip()
        if not value_as_text or value_as_text.lower() in {'nan', 'nat', 'none'}:
            return None

        parsed = pd.to_datetime(value_as_text, format='%Y%m%d', errors='coerce')
        if pd.isna(parsed):
            parsed = pd.to_datetime(value_as_text, errors='coerce')
        if pd.isna(parsed):
            return None
        return parsed.date()

    @staticmethod
    def _deduplicar(registros, key_func):
        deduplicados = {}
        for registro in registros:
            deduplicados[key_func(registro)] = registro
        return list(deduplicados.values())

    @staticmethod
    def _colunas_existentes(df, colunas):
        return [coluna for coluna in colunas if coluna in df.columns]

    @classmethod
    def _validar_schema(cls, dados_limpos):
        erros = []

        for chave, colunas in cls.COLUNAS_OBRIGATORIAS.items():
            df = dados_limpos.get(chave)
            if df is None:
                erros.append(f"Arquivo {chave.upper()} nao foi carregado.")
                continue

            ausentes = [coluna for coluna in colunas if coluna not in df.columns]
            if ausentes:
                erros.append(f"Arquivo {chave.upper()} sem colunas obrigatorias: {', '.join(ausentes)}.")

        if erros:
            raise ValueError(' '.join(erros))
