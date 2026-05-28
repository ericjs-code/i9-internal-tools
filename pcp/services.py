import pandas as pd
import logging
from django.db import transaction
from core.services.protheus_etl import ProtheusBaseETL
from .models import MovimentacaoEstoquePCP, TipoMovimentacao, OrigemMovimentacao

logger = logging.getLogger(__name__)

class PCPEstoqueETLService(ProtheusBaseETL):
    """
    Serviço de ETL para Movimentação de Estoque do PCP.
    Extrai dados do Protheus, transforma via Pandas para otimização de memória,
    e realiza carga do tipo UPSERT no Data Mart em Django.
    """
    ARQUIVOS_ALVO = ['SD1', 'SD2', 'SD3']

    @classmethod
    def transformar_e_salvar(cls, dados_brutos: dict):
        logger.info(f"[{cls.__name__}] Iniciando transformação de dados...")
        dfs = []

        # Processamento SD1 (Notas Fiscais de Entrada)
        if 'SD1' in dados_brutos:
            logger.info(f"[{cls.__name__}] Processando tabela SD1...")
            df_sd1 = dados_brutos['SD1']
            
            colunas_esperadas = ['D1_COD', 'D1_DTDIGIT', 'D1_QUANT', 'D1_DOC']
            if all(col in df_sd1.columns for col in colunas_esperadas):
                df_sd1 = df_sd1[colunas_esperadas].copy()
                
                df_sd1['produto_codigo'] = df_sd1['D1_COD'].astype(str).str.strip()
                df_sd1['data_movimentacao'] = pd.to_datetime(df_sd1['D1_DTDIGIT'], format='%Y%m%d', errors='coerce').dt.date
                df_sd1['quantidade'] = pd.to_numeric(df_sd1['D1_QUANT'], errors='coerce')
                df_sd1['documento'] = df_sd1['D1_DOC'].astype(str).str.strip()
                df_sd1['tipo_movimentacao'] = TipoMovimentacao.ENTRADA.value
                df_sd1['origem_movimentacao'] = OrigemMovimentacao.NF_ENTRADA.value
                df_sd1['cf_operacao'] = ''
                
                dfs.append(df_sd1.dropna(subset=['produto_codigo', 'data_movimentacao']))
            else:
                 logger.warning(f"[{cls.__name__}] SD1 não contém todas as colunas necessárias. Pulando processamento.")

        # Processamento SD2 (Notas Fiscais de Saída)
        if 'SD2' in dados_brutos:
            logger.info(f"[{cls.__name__}] Processando tabela SD2...")
            df_sd2 = dados_brutos['SD2']
            
            colunas_esperadas = ['D2_COD', 'D2_EMISSAO', 'D2_QUANT', 'D2_DOC']
            if all(col in df_sd2.columns for col in colunas_esperadas):
                df_sd2 = df_sd2[colunas_esperadas].copy()
                
                df_sd2['produto_codigo'] = df_sd2['D2_COD'].astype(str).str.strip()
                df_sd2['data_movimentacao'] = pd.to_datetime(df_sd2['D2_EMISSAO'], format='%Y%m%d', errors='coerce').dt.date
                df_sd2['quantidade'] = pd.to_numeric(df_sd2['D2_QUANT'], errors='coerce')
                df_sd2['documento'] = df_sd2['D2_DOC'].astype(str).str.strip()
                df_sd2['tipo_movimentacao'] = TipoMovimentacao.SAIDA.value
                df_sd2['origem_movimentacao'] = OrigemMovimentacao.NF_SAIDA.value
                df_sd2['cf_operacao'] = ''
                
                dfs.append(df_sd2.dropna(subset=['produto_codigo', 'data_movimentacao']))
            else:
                 logger.warning(f"[{cls.__name__}] SD2 não contém todas as colunas necessárias. Pulando processamento.")

        # Processamento SD3 (Movimentações Internas)
        if 'SD3' in dados_brutos:
             logger.info(f"[{cls.__name__}] Processando tabela SD3...")
             df_sd3 = dados_brutos['SD3']
             
             colunas_esperadas = ['D3_COD', 'D3_EMISSAO', 'D3_QUANT', 'D3_DOC', 'D3_TM', 'D3_CF']
             if all(col in df_sd3.columns for col in colunas_esperadas):
                 df_sd3 = df_sd3[colunas_esperadas].copy()
                 
                 df_sd3['produto_codigo'] = df_sd3['D3_COD'].astype(str).str.strip()
                 df_sd3['data_movimentacao'] = pd.to_datetime(df_sd3['D3_EMISSAO'], format='%Y%m%d', errors='coerce').dt.date
                 df_sd3['quantidade'] = pd.to_numeric(df_sd3['D3_QUANT'], errors='coerce')
                 df_sd3['documento'] = df_sd3['D3_DOC'].astype(str).str.strip()
                 df_sd3['cf_operacao'] = df_sd3['D3_CF'].astype(str).str.strip()
                 df_sd3['origem_movimentacao'] = OrigemMovimentacao.MOV_INTERNA.value
                 
                 # REGRA DE NEGÓCIO ATUALIZADA: RE = Requisição (Saída), DE = Devolução (Entrada)
                 # O campo D3_TM (Tipo de Movimento) define a regra.
                 df_sd3['tipo_movimentacao'] = df_sd3['D3_TM'].apply(
                     lambda x: TipoMovimentacao.SAIDA.value if x == 'RE' else TipoMovimentacao.ENTRADA.value
                 )
                 
                 dfs.append(df_sd3.dropna(subset=['produto_codigo', 'data_movimentacao']))
             else:
                  logger.warning(f"[{cls.__name__}] SD3 não contém todas as colunas necessárias. Pulando processamento.")

        if not dfs:
             logger.warning(f"[{cls.__name__}] Nenhum dado processado de SD1, SD2 ou SD3.")
             return False

        logger.info(f"[{cls.__name__}] Concatenando e agregando DataFrames...")
        df_final = pd.concat(dfs, ignore_index=True)
        
        colunas_agrupamento = ['produto_codigo', 'data_movimentacao', 'tipo_movimentacao', 'origem_movimentacao', 'documento', 'cf_operacao']
        df_final = df_final.groupby(colunas_agrupamento, as_index=False)['quantidade'].sum()

        logger.info(f"[{cls.__name__}] Iniciando carga UPSERT no Data Mart ({len(df_final)} registros)...")
        cls._realizar_upsert_lote(df_final)
        
        logger.info(f"[{cls.__name__}] ETL finalizado com sucesso.")
        return True

    @classmethod
    def _realizar_upsert_lote(cls, df: pd.DataFrame):
        """
        Realiza a inserção e atualização massiva no banco de dados.
        """
        BATCH_SIZE = 2000
        registros_preparados = []
        
        for _, row in df.iterrows():
             doc = row['documento'] if pd.notna(row['documento']) and row['documento'] != 'nan' else ''
             cf = row['cf_operacao'] if pd.notna(row['cf_operacao']) and row['cf_operacao'] != 'nan' else ''
             
             obj = MovimentacaoEstoquePCP(
                 produto_codigo=row['produto_codigo'],
                 data_movimentacao=row['data_movimentacao'],
                 tipo_movimentacao=row['tipo_movimentacao'],
                 origem_movimentacao=row['origem_movimentacao'],
                 quantidade=row['quantidade'],
                 documento=doc,
                 cf_operacao=cf
             )
             registros_preparados.append(obj)

        with transaction.atomic():
             MovimentacaoEstoquePCP.objects.bulk_create(
                 registros_preparados,
                 batch_size=BATCH_SIZE,
                 update_conflicts=True,
                 unique_fields=['produto_codigo', 'data_movimentacao', 'documento', 'origem_movimentacao', 'cf_operacao'],
                 update_fields=['quantidade']
             )
