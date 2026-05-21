import os
import pandas as pd
import numpy as np
import logging
from django.conf import settings
from datetime import datetime
from django.db import transaction
from compras.models import DataWarehouseCompras, OperacaoCompras
from core.services.protheus_etl import ProtheusBaseETL

logger = logging.getLogger(__name__)


class ComprasETLService(ProtheusBaseETL):
    """
    Serviço de ETL do Domínio de Compras.
    Herda toda a lógica de conexão, extração e sanitização do Core.
    """

    ARQUIVOS_ALVO = [
        'sc10101.sdb', 'sc70101.sdb', 'sa20101.sdb',
        'sd10101.sdb', 'afg0101.sdb', 'sb10101.sdb', 'sx50101.sdb'
    ]

    @classmethod
    def transformar_e_salvar(cls, dados_limpos: dict):
        """Implementação obrigatória do Template Method do Core"""
        logger.info("[COMPRAS] Iniciando processamento das regras de negócio (DW e Operacional)...")

        # O Core nos entrega um dicionário limpo, sem D_E_L_E_T_, decodificado e sem espaços em branco.
        df_dw = cls._processar_dw(dados_limpos)
        df_operacional = cls._processar_operacional(dados_limpos)

        cls._exportar_relatorios(df_dw, df_operacional)

        cls._salvar_no_banco(df_dw, df_operacional)

        logger.info("[COMPRAS] Processamento e exportação concluídos com sucesso.")
        return True

    @classmethod
    def _salvar_no_banco(cls, df_dw: pd.DataFrame, df_op: pd.DataFrame):
        logger.info("[COMPRAS] Convertendo DataFrames para registros ORM...")

        # Converte DataFrames para dicionários (Vetorização para performance)
        dw_records = df_dw.to_dict('records')
        op_records = df_op.to_dict('records')

        # Funções utilitárias locais para limpeza
        def limpa_data(val):
            val_str = str(val).strip()
            if val_str and val_str not in ['-', 'nan', 'NaT', 'None']:
                try:
                    return datetime.strptime(val_str, '%d/%m/%Y').date()
                except ValueError:
                    return None
            return None

        # Criação dos registros usando compreensão de lista (Muito mais rápido que iterrows)
        registros_dw = [
            DataWarehouseCompras(
                filial=str(r.get('Filial', '')).strip(),
                num_sc=str(r.get('Num_SC', '')).strip(),
                cod_produto=str(r.get('Cod_Produto', '')).strip(),
                descricao=str(r.get('Descricao', '')).strip(),
                projeto_cod=str(r.get('Projeto_Cod', '')).strip(),
                tarefa_cod=str(r.get('Tarefa_Cod', '')).strip(),
                num_pedido=str(r.get('Num_Pedido', '')).strip(),
                cod_fornecedor=str(r.get('Cod_Fornecedor', '')).strip(),
                nome_fornecedor=str(r.get('Nome_Fornecedor', '')).strip(),
                status=str(r.get('Status', '')).strip(),
                emissao_sc=limpa_data(r.get('Emissao_SC')),
                emissao_pedido=limpa_data(r.get('Emissao_Pedido')),
                data_prev_recebimento_fisico=limpa_data(r.get('Data_Prev_Recebimento_Fisico')),
                data_recebimento_real=limpa_data(r.get('Data_Recebimento_Real')),
                qtd_solicitada=float(r.get('Qtd_Solicitada') or 0),
                qtd_pedido=float(r.get('Qtd_Pedido') or 0),
                qtd_recebida=float(r.get('Qtd_Recebida') or 0),
                valor_unitario=float(r.get('Valor_Unitario') or 0),
                valor_total=float(r.get('Valor_Total') or 0),
                leadtime_compras=int(r.get('LeadTime_Compras') or 0),
                leadtime_fornecedor=int(r.get('LeadTime_Fornecedor') or 0),
                dias_atraso_entrega=int(r.get('Dias_Atraso_Entrega') or 0)
            ) for r in dw_records
        ]

        registros_op = [
            OperacaoCompras(
                filial=str(r.get('Filial', '')).strip(),
                num_sc=str(r.get('Num_SC', '')).strip(),
                item_sc=str(r.get('Item_SC', '')).strip(),
                cod_produto=str(r.get('Cod_Produto', '')).strip(),
                descricao=str(r.get('Descricao', '')).strip(),
                projeto_cod=str(r.get('Projeto_Cod', '')).strip(),
                tarefa_cod=str(r.get('Tarefa_Cod', '')).strip(),
                num_pedidos_vinculados=str(r.get('Num_Pedidos_Vinculados', '')).strip(),
                notas_fiscais=str(r.get('Notas_Fiscais', '')).strip(),
                nome_fornecedor=str(r.get('Nome_Fornecedor', '')).strip(),
                status_operacional=str(r.get('Status_Operacional', '')).strip(),
                emissao_sc=limpa_data(r.get('Emissao_SC')),
                emissao_ultimo_pedido=limpa_data(r.get('Emissao_Ultimo_Pedido')),
                previsao_entrega=limpa_data(r.get('Previsao_Entrega')),
                ultima_entrega_real=limpa_data(r.get('Ultima_Entrega_Real')),
                qtd_solicitada=float(r.get('Qtd_Solicitada') or 0),
                qtd_pedida=float(r.get('Qtd_Pedida') or 0),
                qtd_recebida=float(r.get('Qtd_Recebida') or 0),
                saldo_a_comprar=float(r.get('Saldo_A_Comprar') or 0),
                residuo=float(r.get('Residuo') or 0),
                cnpj=str(r.get('cnpj', '')).strip(),
                tipo_produto=str(r.get('tipo_produto', '')).strip(),
            ) for r in op_records
        ]

        with transaction.atomic():
            logger.info("[COMPRAS] Realizando Full Refresh das tabelas...")
            DataWarehouseCompras.objects.all().delete()
            OperacaoCompras.objects.all().delete()
            DataWarehouseCompras.objects.bulk_create(registros_dw, batch_size=2000)
            OperacaoCompras.objects.bulk_create(registros_op, batch_size=2000)
            logger.info("[COMPRAS] Persistência concluída.")

    @classmethod
    def _processar_dw(cls, dados_brutos: dict) -> pd.DataFrame:
        """Regra de negócio do Dashboard Gerencial (DW)"""

        df_sc1 = dados_brutos['sc1'].copy()
        df_sc7 = dados_brutos['sc7'].copy()
        df_sa2 = dados_brutos['sa2'].copy()
        df_sd1 = dados_brutos['sd1'].copy()
        df_afg = dados_brutos['afg'].copy()

        df_sd1['D1_QUANT'] = pd.to_numeric(df_sd1['D1_QUANT'], errors='coerce').fillna(0)
        df_sd1_agg = df_sd1.groupby(['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC']).agg(
            QTD_RECEBIDA=('D1_QUANT', 'sum'),
            DATA_RECEBIMENTO_REAL=('D1_DTDIGIT', 'max')
        ).reset_index()

        # Blindagem de Fornecedor DW
        df_sa2_unico = df_sa2.drop_duplicates(subset=['A2_COD']).copy()
        df_sa2_unico['A2_COD'] = df_sa2_unico['A2_COD'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(
            6)

        if 'AFG_NUMSC' in df_afg.columns:
            df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC'])
        else:
            df_afg_unique = pd.DataFrame(columns=['AFG_NUMSC', 'AFG_ITEMSC', 'AFG_PROJET', 'AFG_TAREFA'])

        df_merged = pd.merge(df_sc1, df_sc7, how='left', left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'], right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])
        df_merged = pd.merge(df_merged, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'], right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
        df_merged['PROJETO_CODIGO'] = df_merged.get('AFG_PROJET', '')
        df_merged['TAREFA_CODIGO'] = df_merged.get('AFG_TAREFA', '')

        # Cruzamento Blindado
        df_merged['C7_FORNECE'] = df_merged['C7_FORNECE'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(
            6)
        df_merged = pd.merge(df_merged, df_sa2_unico, how='left', left_on='C7_FORNECE', right_on='A2_COD')
        df_merged['A2_NOME'] = df_merged['A2_NOME'].fillna('FORNECEDOR NÃO ENCONTRADO')

        df_merged = pd.merge(df_merged, df_sd1_agg, how='left', left_on=['C7_FILIAL', 'C7_NUM', 'C7_ITEM'], right_on=['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC'])

        def convert_date(serie):
            return pd.to_datetime(serie, format='%Y%m%d', errors='coerce')

        df_merged['DATA_SC_REAL'] = convert_date(df_merged.get('C1_EMISSAO'))
        df_merged['DATA_PEDIDO_REAL'] = convert_date(df_merged.get('C7_EMISSAO'))
        df_merged['DATA_PREV_RECEBIMENTO'] = convert_date(df_merged.get('C7_DATPRF'))
        df_merged['DATA_RECEBIMENTO_REAL_DT'] = convert_date(df_merged.get('DATA_RECEBIMENTO_REAL'))

        df_merged['STATUS_COMPRA'] = np.where(df_merged['C7_NUM'].isna() | (df_merged['C7_NUM'] == ''), 'PENDENTE', 'COM PEDIDO')
        df_merged['STATUS_COMPRA'] = np.where(df_merged['DATA_RECEBIMENTO_REAL_DT'].notna(), 'ENTREGUE', df_merged['STATUS_COMPRA'])

        df_merged['DIAS_LEAD_TIME'] = (df_merged['DATA_PEDIDO_REAL'] - df_merged['DATA_SC_REAL']).dt.days.fillna(0).astype(int)
        df_merged['DIAS_LEAD_FORNECEDOR'] = (df_merged['DATA_PREV_RECEBIMENTO'] - df_merged['DATA_PEDIDO_REAL']).dt.days.fillna(0).astype(int)
        df_merged['DIAS_ATRASO_ENTREGA'] = (df_merged['DATA_RECEBIMENTO_REAL_DT'] - df_merged['DATA_PREV_RECEBIMENTO']).dt.days.fillna(0).astype(int)

        colunas_map = {
            'C1_FILIAL': 'Filial', 'C1_NUM': 'Num_SC', 'C1_PRODUTO': 'Cod_Produto', 'C1_DESCRI': 'Descricao',
            'C1_QUANT': 'Qtd_Solicitada', 'PROJETO_CODIGO': 'Projeto_Cod', 'TAREFA_CODIGO': 'Tarefa_Cod',
            'C7_NUM': 'Num_Pedido', 'C7_FORNECE': 'Cod_Fornecedor', 'A2_NOME': 'Nome_Fornecedor',
            'A2_CGC': 'CNPJ', 'C7_QUANT': 'Qtd_Pedido', 'QTD_RECEBIDA': 'Qtd_Recebida',
            'C7_PRECO': 'Valor_Unitario', 'C7_TOTAL': 'Valor_Total', 'STATUS_COMPRA': 'Status',
            'DIAS_LEAD_TIME': 'LeadTime_Compras', 'DIAS_LEAD_FORNECEDOR': 'LeadTime_Fornecedor',
            'DIAS_ATRASO_ENTREGA': 'Dias_Atraso_Entrega'
        }

        df_merged['Emissao_SC'] = df_merged['DATA_SC_REAL'].dt.strftime('%d/%m/%Y').fillna('-')
        df_merged['Emissao_Pedido'] = df_merged['DATA_PEDIDO_REAL'].dt.strftime('%d/%m/%Y').fillna('-')
        df_merged['Data_Prev_Recebimento_Fisico'] = df_merged['DATA_PREV_RECEBIMENTO'].dt.strftime('%d/%m/%Y').fillna('-')
        df_merged['Data_Recebimento_Real'] = df_merged['DATA_RECEBIMENTO_REAL_DT'].dt.strftime('%d/%m/%Y').fillna('-')

        df_final = df_merged.rename(columns=colunas_map)
        cols_finais = list(colunas_map.values()) + ['Emissao_SC', 'Emissao_Pedido', 'Data_Prev_Recebimento_Fisico','Data_Recebimento_Real']
        df_final = df_final[[c for c in cols_finais if c in df_final.columns]]

        for col in ['Qtd_Solicitada', 'Qtd_Pedido', 'Qtd_Recebida', 'Valor_Unitario', 'Valor_Total']:
            if col in df_final.columns:
                df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

        return df_final

    @classmethod
    def _processar_operacional(cls, dados_brutos: dict) -> pd.DataFrame:
        """Regra de negócio da Tabela Operacional e Avaliações"""
        df_sc1 = dados_brutos['sc1'].copy()
        df_sc7 = dados_brutos['sc7'].copy()
        df_sa2 = dados_brutos['sa2'].copy()
        df_sd1 = dados_brutos['sd1'].copy()
        df_afg = dados_brutos['afg'].copy()
        df_sb1 = dados_brutos['sb1'].copy()
        df_sx5 = dados_brutos['sx5'].copy()

        df_sb1_mini = df_sb1[['B1_COD', 'B1_TIPO']].drop_duplicates()

        df_sx5_mini = df_sx5[df_sx5['X5_TABELA'] == '02'][['X5_CHAVE', 'X5_DESCRI']].drop_duplicates()
        df_produtos_tipo = pd.merge(df_sb1_mini, df_sx5_mini, how='left', left_on='B1_TIPO', right_on='X5_CHAVE')

        df_sd1['D1_QUANT'] = pd.to_numeric(df_sd1['D1_QUANT'], errors='coerce').fillna(0)
        df_sd1['D1_TOTAL'] = pd.to_numeric(df_sd1['D1_TOTAL'], errors='coerce').fillna(0)
        df_sc7['C7_QUANT'] = pd.to_numeric(df_sc7['C7_QUANT'], errors='coerce').fillna(0)
        df_sc1['C1_QUANT'] = pd.to_numeric(df_sc1['C1_QUANT'], errors='coerce').fillna(0)

        df_sd1_agg = df_sd1.groupby(['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC']).agg(
            QTD_RECEBIDA_TOTAL=('D1_QUANT', 'sum'),
            VALOR_RECEBIDO_TOTAL=('D1_TOTAL', 'sum'),
            NOTAS_FISCAIS=('D1_DOC', lambda x: ', '.join(x.dropna().unique())),
            DATA_ULTIMA_ENTREGA=('D1_DTDIGIT', 'max')
        ).reset_index()

        df_sc7_sd1 = pd.merge(df_sc7, df_sd1_agg, how='left', left_on=['C7_FILIAL', 'C7_NUM', 'C7_ITEM'],
                              right_on=['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC'])
        df_sc7_sd1 = pd.merge(df_sc7_sd1, df_produtos_tipo, how='left', left_on='C7_PRODUTO', right_on='B1_COD')

        df_sc7_sd1['QTD_RECEBIDA_TOTAL'] = df_sc7_sd1['QTD_RECEBIDA_TOTAL'].fillna(0)
        df_sc7_sd1['VALOR_RECEBIDO_TOTAL'] = df_sc7_sd1['VALOR_RECEBIDO_TOTAL'].fillna(0)
        df_sc7_sd1['C7_FORNECE'] = df_sc7_sd1['C7_FORNECE'].replace(r'^\s*$', np.nan, regex=True)

        df_sc7_agg = df_sc7_sd1.groupby(['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC']).agg(
            QTD_PEDIDA_TOTAL=('C7_QUANT', 'sum'),
            QTD_RECEBIDA_TOTAL=('QTD_RECEBIDA_TOTAL', 'sum'),
            VALOR_RECEBIDO_TOTAL=('VALOR_RECEBIDO_TOTAL', 'sum'),
            NUM_PEDIDOS_VINCULADOS=('C7_NUM', lambda x: ', '.join(x.dropna().unique())),
            NOTAS_FISCAIS=('NOTAS_FISCAIS', lambda x: ', '.join([str(i) for i in x.dropna().unique() if str(i) != ''])),
            COD_FORNECEDOR=('C7_FORNECE', 'first'),
            DATA_ULTIMO_PEDIDO=('C7_EMISSAO', 'max'),
            PREVISAO_ENTREGA=('C7_DATPRF', 'max'),
            DATA_ULTIMA_ENTREGA=('DATA_ULTIMA_ENTREGA', 'max'),
            TIPO_PRODUTO=('X5_DESCRI',
                          lambda x: ', '.join([str(i).strip() for i in x.dropna().unique() if str(i).strip() != '']))
        ).reset_index()

        df_op = pd.merge(df_sc1, df_sc7_agg, how='left', left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'],
                         right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])

        df_op['QTD_PEDIDA_TOTAL'] = df_op['QTD_PEDIDA_TOTAL'].fillna(0).round(3)
        df_op['QTD_RECEBIDA_TOTAL'] = df_op['QTD_RECEBIDA_TOTAL'].fillna(0).round(3)
        df_op['VALOR_RECEBIDO_TOTAL'] = df_op['VALOR_RECEBIDO_TOTAL'].fillna(0)

        # Limpeza Blindada do Fornecedor Operacional
        df_sa2_mini = df_sa2.drop_duplicates(subset=['A2_COD'])[['A2_COD', 'A2_NOME', 'A2_CGC']].copy()
        df_op['COD_FORNECEDOR'] = df_op['COD_FORNECEDOR'].astype(str).str.split('.').str[0].str.replace(r'\D', '',
                                                                                                        regex=True).str.zfill(
            6)
        df_sa2_mini['A2_COD'] = df_sa2_mini['A2_COD'].astype(str).str.split('.').str[0].str.replace(r'\D', '',
                                                                                                    regex=True).str.zfill(
            6)

        df_op = pd.merge(df_op, df_sa2_mini, how='left', left_on='COD_FORNECEDOR', right_on='A2_COD')
        df_op['NOME_FORNECEDOR_FINAL'] = df_op['A2_NOME'].fillna('FORNECEDOR NÃO ENCONTRADO')

        if 'AFG_NUMSC' in df_afg.columns:
            df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC']).copy()
            df_op = pd.merge(df_op, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'],
                             right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
            df_op['PROJETO_CODIGO'] = df_op['AFG_PROJET']
        else:
            df_op['PROJETO_CODIGO'], df_op['AFG_TAREFA'] = '', ''

        df_op['SALDO_A_COMPRAR'] = (df_op['C1_QUANT'] - df_op['QTD_PEDIDA_TOTAL']).clip(lower=0)
        df_op['RESIDUO'] = (df_op['C1_QUANT'] - df_op['QTD_PEDIDA_TOTAL']).clip(lower=0).round(3)

        condicoes = [
            (df_op['QTD_PEDIDA_TOTAL'] == 0),
            (df_op['QTD_PEDIDA_TOTAL'] < df_op['C1_QUANT']) & (df_op['QTD_PEDIDA_TOTAL'] > 0),
            (df_op['QTD_PEDIDA_TOTAL'] >= df_op['C1_QUANT']) & (df_op['QTD_RECEBIDA_TOTAL'] == 0),
            (df_op['QTD_PEDIDA_TOTAL'] >= df_op['C1_QUANT']) & (df_op['QTD_RECEBIDA_TOTAL'] > 0) & (
                        df_op['QTD_RECEBIDA_TOTAL'] < df_op['QTD_PEDIDA_TOTAL']),
            (df_op['QTD_RECEBIDA_TOTAL'] >= df_op['C1_QUANT'])
        ]
        resultados = ['PENDENTE COTAÇÃO', 'COMPRA PARCIAL', 'AGUARDANDO ENTREGA', 'ENTREGA PARCIAL', 'ATENDIDO TOTAL']
        df_op['STATUS_OPERACIONAL'] = np.select(condicoes, resultados, default='DESCONHECIDO')

        def formatar_data(serie):
            return pd.to_datetime(serie, format='%Y%m%d', errors='coerce').dt.strftime('%d/%m/%Y').fillna('-')

        df_op['EMISSAO_SC_FMT'] = formatar_data(df_op['C1_EMISSAO'])
        df_op['EMISSAO_PEDIDO_FMT'] = formatar_data(df_op['DATA_ULTIMO_PEDIDO'])
        df_op['PREVISAO_ENTREGA_FMT'] = formatar_data(df_op['PREVISAO_ENTREGA'])
        df_op['ENTREGA_REAL_FMT'] = formatar_data(df_op['DATA_ULTIMA_ENTREGA'])

        mapa_colunas = {
            'C1_FILIAL': 'Filial', 'C1_NUM': 'Num_SC', 'C1_ITEM': 'Item_SC',
            'C1_PRODUTO': 'Cod_Produto', 'C1_DESCRI': 'Descricao', 'PROJETO_CODIGO': 'Projeto_Cod',
            'NOTAS_FISCAIS': 'Notas_Fiscais', 'AFG_TAREFA': 'Tarefa_Cod',
            'NUM_PEDIDOS_VINCULADOS': 'Num_Pedidos_Vinculados', 'NOME_FORNECEDOR_FINAL': 'Nome_Fornecedor',
            'A2_CGC': 'cnpj', 'TIPO_PRODUTO': 'tipo_produto', 'STATUS_OPERACIONAL': 'Status_Operacional',
            'EMISSAO_SC_FMT': 'Emissao_SC', 'EMISSAO_PEDIDO_FMT': 'Emissao_Ultimo_Pedido',
            'PREVISAO_ENTREGA_FMT': 'Previsao_Entrega', 'ENTREGA_REAL_FMT': 'Ultima_Entrega_Real',
            'C1_QUANT': 'Qtd_Solicitada', 'QTD_PEDIDA_TOTAL': 'Qtd_Pedida',
            'QTD_RECEBIDA_TOTAL': 'Qtd_Recebida', 'SALDO_A_COMPRAR': 'Saldo_A_Comprar',
            'RESIDUO': 'Residuo'
        }

        df_final = df_op.rename(columns=mapa_colunas)[list(mapa_colunas.values())]
        return df_final

    @classmethod
    def _exportar_relatorios(cls, df_dw: pd.DataFrame, df_operacional: pd.DataFrame):
        """Gera os arquivos Excel no diretório de Mídia do Django"""

        # Cria pasta específica para os relatórios de compras dentro do MEDIA_ROOT
        diretorio_saida = os.path.join(settings.MEDIA_ROOT, 'compras', 'relatorios')
        os.makedirs(diretorio_saida, exist_ok=True)

        caminho_dw = os.path.join(diretorio_saida, 'report_SC_x_PC.xlsx')
        caminho_op = os.path.join(diretorio_saida, 'report_operacional.xlsx')

        logger.info("[COMPRAS] Gravando arquivos Excel no disco/storage...")

        df_dw.to_excel(caminho_dw, index=False)
        df_operacional.to_excel(caminho_op, index=False)

        logger.info(f"[COMPRAS] Relatórios exportados com sucesso em {diretorio_saida}")