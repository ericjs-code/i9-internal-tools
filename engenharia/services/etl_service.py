import logging
import pandas as pd
from django.db import transaction
from engenharia.models import EstruturaProduto
from core.services.protheus_etl import ProtheusBaseETL


logger = logging.getLogger(__name__)

class EngenhariaETLService(ProtheusBaseETL):
    """
    Serviço de ETL do dominio de engenharia
    Herda o Template Method Corporativo
    """

# Declaramos as tabelas a serem extraidas
    ARQUIVOS_ALVO = ["sg10101.sdb", 'sb10101.sdb']

    @classmethod
    def transformar_e_salvar(cls, dados_limpos:dict):
        """Implemetação obrigatoria do Template Method Corporativo"""
        logger.info("[ENGENHARIA] Iniciando processamento de Estrutura de Produtos")

        df_estruturada = cls._processar_estrutura(dados_limpos)

        cls._salvar_no_banco(df_estruturada)

        logger.info("[ENGENHARIA] ETL finalizado com sucesso")
        return True


    @classmethod
    def _processar_estrutura(cls, dados_brutos:dict) -> pd.DataFrame:
        """Regra de negocio pura do pandas, limpa e vetorizada"""
        df_sg1 = dados_brutos['sg1'].copy()
        df_sb1 = dados_brutos['sb1'].copy()

        df_sb1_mini = df_sb1[['B1_COD', 'B1_DESC', 'B1_TIPO', 'B1_UM']].drop_duplicates(subset='B1_COD')

        # Merge do COMPONENTE (Pai)
        df_merge_pai = pd.merge(df_sg1, df_sb1_mini, how='left', left_on='G1_COD', right_on='B1_COD')
        df_merge_pai = df_merge_pai.rename(columns={
            'G1_COD': 'CODIGO_PAI', 'B1_DESC': 'DESC_PAI',
            'B1_TIPO': 'TIPO_PAI', 'B1_UM': 'UM_PAI'
        }).drop(columns=['B1_COD'], errors='ignore')

        # Merge do COMPONENTE (Filho)
        df_final = pd.merge(df_merge_pai, df_sb1_mini, how='left', left_on='G1_COMP', right_on='B1_COD')
        df_final = df_final.rename(columns={
            'G1_COMP': 'CODIGO_COMPONENTE', 'B1_DESC': 'DESC_COMPONENTE',
            'B1_TIPO': 'TIPO_COMPONENTE', 'G1_QUANT': 'QTD_NECESSARIA',
            'B1_UM': 'UM_COMPONENTE', 'G1_NIV': 'NIVEL', 'G1_PERDA': 'PERDA', 'G1_FIXO': 'TIPO_QTD'
        })

        df_final['QTD_NECESSARIA'] = pd.to_numeric(df_final['QTD_NECESSARIA'], errors='coerce').fillna(0)
        df_final['PERDA'] = pd.to_numeric(df_final['PERDA'], errors='coerce').fillna(0)

        df_final.fillna('', inplace=True)

        return df_final

    @classmethod
    def _salvar_no_banco(cls, df: pd.DataFrame):
        """Salva os registros de forma otimizada"""

        logger.info("[ENGENHARIA] Convertendo DataFrame para registro ORM...")
        records = df.to_dict('records')

        registros_orm = [
            EstruturaProduto(
                # --- PAI ---
                codigo_pai=str(rec.get('CODIGO_PAI', '')).strip(),
                descricao_pai=str(rec.get('DESC_PAI', '')).strip(),
                tipo_pai=str(rec.get('TIPO_PAI', '')).strip(),
                unidade_pai=str(rec.get('UM_PAI', '')).strip(),

                # --- FILHO / COMPONENTE ---
                nivel=str(rec.get('NIVEL', '')).strip(),
                codigo_componente=str(rec.get('CODIGO_COMPONENTE', '')).strip(),
                descricao_componente=str(rec.get('DESC_COMPONENTE', '')).strip(),
                tipo_componente=str(rec.get('TIPO_COMPONENTE', '')).strip(),
                unidade_medida_filho=str(rec.get('UM_COMPONENTE', '')).strip(),
                tipo_quantidade=str(rec.get('TIPO_QTD', '')).strip(),

                # --- NUMÉRICOS (Cast correto para Float, com fallback seguro para 0.0) ---
                quantidade_necessaria=float(rec.get('QTD_NECESSARIA', 0.0) or 0.0),
                quantidade=float(rec.get('QTD_NECESSARIA', 0.0) or 0.0),
                perda_percentual=float(rec.get('PERDA', 0.0) or 0.0),
            )
            for rec in records
        ]

        with transaction.atomic():
            logger.info("[ENGENHARIA] Realizando Full Refresh...")
            EstruturaProduto.objects.all().delete()
            # bulk_create insere no Postgres em lotes com altíssima performance
            EstruturaProduto.objects.bulk_create(registros_orm, batch_size=2000)