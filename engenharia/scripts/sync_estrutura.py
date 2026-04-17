import os
import pandas as pd
import sqlite3
from core.utils.sftp_client import baixar_arquivos_sftp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
EXCEL_PATH = os.path.join(DATA_DIR, 'report_estrutura_simples.xlsx')

ARQUIVOS_ALVOS = ['sg10101.sdb', 'sb10101.sdb']


def extrair_dados_engenharia():
    baixar_arquivos_sftp(arquivos_alvo=ARQUIVOS_ALVOS, diretorio_destino=DATA_DIR)


def ler_tabelas(nome_arquivo):
    caminho = os.path.join(DATA_DIR, nome_arquivo)
    con = sqlite3.connect(caminho)
    con.text_factory = bytes
    cursor = con.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    table_name = cursor.fetchone()[0].decode('latin1', errors='ignore')
    df = pd.read_sql(f"SELECT * FROM {table_name}", con)
    con.close()

    def clean_bytes(valor):
        return valor.decode('latin1', errors='ignore') if isinstance(valor, bytes) else valor

    df = df.map(clean_bytes) if hasattr(df, 'map') else df.applymap(clean_bytes)
    df.columns = df.columns.str.strip().str.upper()
    return df.astype(str)


def processar_estrutura():
    print("[ETL] Lendo tabelas...")
    df_sg1 = ler_tabelas('sg10101.sdb')
    df_sb1 = ler_tabelas('sb10101.sdb')

    # EXTRAÇÃO
    df_sb1_mini = df_sb1[['B1_COD', 'B1_DESC', 'B1_TIPO', 'B1_UM']]

    # MERGE PAI
    df_merge_pai = pd.merge(
        df_sg1,
        df_sb1_mini,
        how='left',
        left_on='G1_COD',
        right_on='B1_COD'
    )

    # TRANSFORMAÇÃO
    df_merge_pai = df_merge_pai.rename(columns={
        'G1_COD': 'CODIGO_PAI',
        'B1_DESC': 'DESC_PAI',
        'B1_TIPO': 'TIPO_PAI',
        'B1_UM': 'UM_PAI'
    })

    df_merge_pai = df_merge_pai.drop(columns=['B1_COD'], errors='ignore')

    # MERGE 2: BUSCANDO OS DADOS DO COMPONENTE
    df_final = pd.merge(
        df_merge_pai,
        df_sb1_mini,
        how='left',
        left_on='G1_COMP',
        right_on='B1_COD'
    )

    # Renomeando as colunas referentes ao filho
    df_final = df_final.rename(columns={
        'G1_COMP': 'CODIGO',
        'B1_DESC': 'DESCRICAO',
        'B1_TIPO': 'TP',
        'G1_QUANT': 'QTDE.NECESSARIA',
        'B1_UM': 'UM_COMPONENTE'
    })

    # Exportando o resultado limpo
    df_final.to_excel(EXCEL_PATH, index=False)
    print(f"[ETL] Sucesso! Relatório salvo em: {EXCEL_PATH}")


if __name__ == "__main__":
    print("INICIANDO PIPELINE DE ENGENHARIA")
    extrair_dados_engenharia()
    processar_estrutura()
    print("=== PIPELINE FINALIZADO ===")