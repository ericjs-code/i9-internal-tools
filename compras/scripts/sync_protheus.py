import os
import paramiko
import pandas as pd
import numpy as np
import sqlite3
import requests
from dotenv import load_dotenv
import os

load_dotenv()

SFTP_HOST = os.getenv('SFTP_HOST')
SFTP_PORT = os.getenv('SFTP_PORT', 1401)
SFTP_USER = os.getenv('SFTP_USER')
SFTP_PASS = os.getenv('SFTP_PASS')
SFTP_REMOTE_DIR = os.getenv('SFTP_REMOTE_DIR')

API_URL = os.getenv('API_URL')
API_TOKEN = os.getenv('API_TOKEN')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
EXCEL_PATH = os.path.join(DATA_DIR, 'report_SC_x_PC.xlsx')
EXCEL_OPERACIONAL_PATH = os.path.join(DATA_DIR, 'report_operacional.xlsx')

ARQUIVOS_ALVO = [
    'sc10101.sdb', 'sc70101.sdb',
    'sa201011.sdb', 'sd10101.sdb', 'afg0101.sdb'
]


def baixar_dados_totvs():
    os.makedirs(DATA_DIR, exist_ok=True)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print("[1/4] Conectando ao servidor TOTVS via SFTP...")
    try:
        ssh.connect(hostname=SFTP_HOST, port=SFTP_PORT, username=SFTP_USER, password=SFTP_PASS)
        sftp = ssh.open_sftp()
        sftp.chdir(SFTP_REMOTE_DIR)

        for arquivo in ARQUIVOS_ALVO:
            print(f"Baixando {arquivo}...")
            sftp.get(arquivo, os.path.join(DATA_DIR, arquivo))

        print("Download concluído.")
    except Exception as e:
        print(f"[ERRO] Falha no SFTP: {e}")
        raise
    finally:
        if 'sftp' in locals(): sftp.close()
        ssh.close()


def ler_tabela_sqlite(nome_arquivo):
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


def processar_dados():
    print("[2/4] Processando e limpando dados (ETL)...")

    # Leitura
    df_sc1 = ler_tabela_sqlite('sc10101.sdb')
    df_sc7 = ler_tabela_sqlite('sc70101.sdb')
    df_sa2 = ler_tabela_sqlite('sa201011.sdb')
    df_sd1 = ler_tabela_sqlite('sd10101.sdb')
    df_afg = ler_tabela_sqlite('afg0101.sdb')

    # Limpeza Padrão Protheus
    for df in [df_sc1, df_sc7, df_sa2, df_sd1, df_afg]:
        if 'D_E_L_E_T_' in df.columns: df.drop(df[df['D_E_L_E_T_'] == '*'].index, inplace=True)
        colunas_remover = [c for c in ['D_E_L_E_T_', 'R_E_C_N_O_', 'R_E_C_D_E_L_'] if c in df.columns]
        df.drop(columns=colunas_remover, inplace=True, errors='ignore')
        for col in df.columns: df[col] = df[col].str.strip()  # Strip geral

    # Merges
    df_merged = pd.merge(df_sc1, df_sc7, how='left', left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'],
                         right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])

    if 'AFG_NUMSC' in df_afg.columns:
        df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC']).copy()
        df_merged = pd.merge(df_merged, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'],
                             right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
        df_merged['PROJETO_CODIGO'] = df_merged['AFG_PROJET']
    else:
        df_merged['PROJETO_CODIGO'], df_merged['AFG_TAREFA'] = '', ''

    df_merged = pd.merge(df_merged, df_sa2, how='left', left_on=['C7_FORNECE', 'C7_LOJA'],
                         right_on=['A2_COD', 'A2_LOJA'])
    df_merged = pd.merge(df_merged, df_sd1, how='left', left_on=['C7_FILIAL', 'C7_NUM', 'C7_ITEM'],
                         right_on=['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC'])

    # Regras de Negócio e Datas
    def convert_date(serie):
        return pd.to_datetime(serie, format='%Y%m%d', errors='coerce')

    df_merged['DATA_SC_REAL'] = convert_date(df_merged.get('C1_EMISSAO', pd.Series(dtype=str)))
    df_merged['DATA_PEDIDO_REAL'] = convert_date(df_merged.get('C7_EMISSAO', pd.Series(dtype=str)))
    df_merged['DATA_PREV_RECEBIMENTO'] = convert_date(df_merged.get('C7_DATPRF', pd.Series(dtype=str)))
    df_merged['DATA_RECEBIMENTO_REAL'] = convert_date(df_merged.get('D1_DTDIGIT', pd.Series(dtype=str)))

    df_merged['STATUS_COMPRA'] = np.where(df_merged['C7_NUM'].isna() | (df_merged['C7_NUM'] == ''), 'PENDENTE',
                                          'COM PEDIDO')
    df_merged['STATUS_COMPRA'] = np.where(df_merged['D1_DTDIGIT'].notna() & (df_merged['D1_DTDIGIT'] != ''), 'ENTREGUE',
                                          df_merged['STATUS_COMPRA'])

    df_merged['DIAS_LEAD_TIME'] = (df_merged['DATA_PEDIDO_REAL'] - df_merged['DATA_SC_REAL']).dt.days.fillna(0).astype(
        int)
    df_merged['DIAS_LEAD_FORNECEDOR'] = (
                df_merged['DATA_PREV_RECEBIMENTO'] - df_merged['DATA_PEDIDO_REAL']).dt.days.fillna(0).astype(int)
    df_merged['DIAS_ATRASO_ENTREGA'] = (
                df_merged['DATA_RECEBIMENTO_REAL'] - df_merged['DATA_PREV_RECEBIMENTO']).dt.days.fillna(0).astype(int)

    # Exportação
    colunas_map = {
        'C1_FILIAL': 'Filial', 'C1_NUM': 'Num_SC', 'C1_PRODUTO': 'Cod_Produto', 'C1_DESCRI': 'Descricao',
        'C1_QUANT': 'Qtd_Solicitada',
        'PROJETO_CODIGO': 'Projeto_Cod', 'AFG_TAREFA': 'Tarefa_Cod', 'C7_NUM': 'Num_Pedido',
        'C7_FORNECE': 'Cod_Fornecedor',
        'A2_NOME': 'Nome_Fornecedor', 'C7_QUANT': 'Qtd_Pedido', 'D1_QUANT': 'Qtd_Recebida',
        'C7_PRECO': 'Valor_Unitario',
        'C7_TOTAL': 'Valor_Total', 'STATUS_COMPRA': 'Status', 'DIAS_LEAD_TIME': 'LeadTime_Compras',
        'DIAS_LEAD_FORNECEDOR': 'LeadTime_Fornecedor', 'DIAS_ATRASO_ENTREGA': 'Dias_Atraso_Entrega'
    }

    # Formatação de datas em string
    df_merged['Emissao_SC'] = df_merged['DATA_SC_REAL'].dt.strftime('%d/%m/%Y')
    df_merged['Emissao_Pedido'] = df_merged['DATA_PEDIDO_REAL'].dt.strftime('%d/%m/%Y').fillna('-')
    df_merged['Data_Prev_Recebimento_Fisico'] = df_merged['DATA_PREV_RECEBIMENTO'].dt.strftime('%d/%m/%Y').fillna('-')
    df_merged['Data_Recebimento_Real'] = df_merged['DATA_RECEBIMENTO_REAL'].dt.strftime('%d/%m/%Y').fillna('-')

    df_final = df_merged.rename(columns=colunas_map)
    cols_existentes = [c for c in
                       list(colunas_map.values()) + ['Emissao_SC', 'Emissao_Pedido', 'Data_Prev_Recebimento_Fisico',
                                                     'Data_Recebimento_Real'] if c in df_final.columns]
    df_final = df_final[cols_existentes]

    for col in ['Qtd_Solicitada', 'Qtd_Pedido', 'Qtd_Recebida', 'Valor_Unitario', 'Valor_Total']:
        if col in df_final.columns: df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

    print(f"[3/4] Gerando arquivo Excel em: {EXCEL_PATH}")
    df_final.to_excel(EXCEL_PATH, index=False, engine='openpyxl')


def processar_dados_operacionais():
    print('[ETL OPERACIONAL] Processando base bottom-up...')

    df_sc1 = ler_tabela_sqlite('sc10101.sdb')
    df_sc7 = ler_tabela_sqlite('sc70101.sdb')
    df_sa2 = ler_tabela_sqlite('sa201011.sdb')
    df_sd1 = ler_tabela_sqlite('sd10101.sdb')
    df_afg = ler_tabela_sqlite('afg0101.sdb')

    for df in [df_sc1, df_sc7, df_sa2, df_sd1, df_afg]:
        if 'D_E_L_E_T_' in df.columns:
            df.drop(df[df['D_E_L_E_T_'] == '*'].index, inplace=True)

        colunas_remover = [c for c in ['D_E_L_E_T_', 'R_E_C_N_O_', 'R_E_C_D_E_L_'] if c in df.columns]
        df.drop(columns=colunas_remover, inplace=True, errors='ignore')
        for col in df.columns: df[col] = df[col].str.strip()

    # Tipagem rigorosa para quantidades e financeiro
    df_sd1['D1_QUANT'] = pd.to_numeric(df_sd1['D1_QUANT'], errors='coerce').fillna(0)
    df_sd1['D1_TOTAL'] = pd.to_numeric(df_sd1['D1_TOTAL'], errors='coerce').fillna(0)  # Financeiro da NF
    df_sc7['C7_QUANT'] = pd.to_numeric(df_sc7['C7_QUANT'], errors='coerce').fillna(0)
    df_sc1['C1_QUANT'] = pd.to_numeric(df_sc1['C1_QUANT'], errors='coerce').fillna(0)

    # Notas Fiscais
    df_sd1_agg = df_sd1.groupby(['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC']).agg(
        QTD_RECEBIDA_TOTAL=('D1_QUANT', 'sum'),
        VALOR_RECEBIDO_TOTAL=('D1_TOTAL', 'sum'),  # Soma Financeira
        NOTAS_FISCAIS=('D1_DOC', lambda x: ', '.join(x.dropna().unique())),
        DATA_ULTIMA_ENTREGA=('D1_DTDIGIT', 'max')
    ).reset_index()

    df_sc7_sd1 = pd.merge(df_sc7, df_sd1_agg, how='left',
                          left_on=['C7_FILIAL', 'C7_NUM', 'C7_ITEM'],
                          right_on=['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC'])

    df_sc7_sd1['QTD_RECEBIDA_TOTAL'] = df_sc7_sd1['QTD_RECEBIDA_TOTAL'].fillna(0)
    df_sc7_sd1['VALOR_RECEBIDO_TOTAL'] = df_sc7_sd1['VALOR_RECEBIDO_TOTAL'].fillna(0)

    # Pedidos
    df_sc7_agg = df_sc7_sd1.groupby(['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC']).agg(
        QTD_PEDIDA_TOTAL=('C7_QUANT', 'sum'),
        QTD_RECEBIDA_TOTAL=('QTD_RECEBIDA_TOTAL', 'sum'),
        VALOR_RECEBIDO_TOTAL=('VALOR_RECEBIDO_TOTAL', 'sum'),
        NUM_PEDIDOS_VINCULADOS=('C7_NUM', lambda x: ', '.join(x.dropna().unique())),
        NOTAS_FISCAIS=('NOTAS_FISCAIS', lambda x: ', '.join([str(i) for i in x.dropna().unique() if str(i) != ''])),
        COD_FORNECEDOR=('C7_FORNECE', 'last'),
        LOJA_FORNECEDOR=('C7_LOJA', 'last'),
        DATA_ULTIMO_PEDIDO=('C7_EMISSAO', 'max'),
        PREVISAO_ENTREGA=('C7_DATPRF', 'max'),
        DATA_ULTIMA_ENTREGA=('DATA_ULTIMA_ENTREGA', 'max')
    ).reset_index()

    # Base Final (Solicitações)
    df_op = pd.merge(df_sc1, df_sc7_agg, how='left',
                     left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'],
                     right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])

    df_op['QTD_PEDIDA_TOTAL'] = df_op['QTD_PEDIDA_TOTAL'].fillna(0).round(3)
    df_op['QTD_RECEBIDA_TOTAL'] = df_op['QTD_RECEBIDA_TOTAL'].fillna(0).round(3)
    df_op['VALOR_RECEBIDO_TOTAL'] = df_op['VALOR_RECEBIDO_TOTAL'].fillna(0)

    # Enriquecimento com Fornecedor e Projeto
    df_op = pd.merge(df_op, df_sa2, how='left', left_on=['COD_FORNECEDOR', 'LOJA_FORNECEDOR'],
                     right_on=['A2_COD', 'A2_LOJA'])

    if 'AFG_NUMSC' in df_afg.columns:
        df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC']).copy()
        df_op = pd.merge(df_op, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'],
                         right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
        df_op['PROJETO_CODIGO'] = df_op['AFG_PROJET']
    else:
        df_op['PROJETO_CODIGO'], df_op['AFG_TAREFA'] = '', ''

    # REGRAS (Saldos e Status Limpo)
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

    # Datas
    def formatar_data(serie):
        return pd.to_datetime(serie, format='%Y%m%d', errors='coerce').dt.strftime('%d/%m/%Y').fillna('-')

    df_op['EMISSAO_SC_FMT'] = formatar_data(df_op['C1_EMISSAO'])
    df_op['EMISSAO_PEDIDO_FMT'] = formatar_data(df_op['DATA_ULTIMO_PEDIDO'])
    df_op['PREVISAO_ENTREGA_FMT'] = formatar_data(df_op['PREVISAO_ENTREGA'])
    df_op['ENTREGA_REAL_FMT'] = formatar_data(df_op['DATA_ULTIMA_ENTREGA'])

    # Mapa Único de Exportação
    mapa_colunas = {
        'C1_FILIAL': 'Filial', 'C1_NUM': 'Num_SC', 'C1_ITEM': 'Item_SC',
        'C1_PRODUTO': 'Cod_Produto', 'C1_DESCRI': 'Descricao',
        'PROJETO_CODIGO': 'Projeto_Cod', 'NOTAS_FISCAIS': 'Notas_Fiscais', 'AFG_TAREFA': 'Tarefa_Cod',
        'NUM_PEDIDOS_VINCULADOS': 'Num_Pedidos_Vinculados', 'A2_NOME': 'Nome_Fornecedor',
        'STATUS_OPERACIONAL': 'Status_Operacional',
        'EMISSAO_SC_FMT': 'Emissao_SC', 'EMISSAO_PEDIDO_FMT': 'Emissao_Ultimo_Pedido',
        'PREVISAO_ENTREGA_FMT': 'Previsao_Entrega', 'ENTREGA_REAL_FMT': 'Ultima_Entrega_Real',
        'C1_QUANT': 'Qtd_Solicitada', 'QTD_PEDIDA_TOTAL': 'Qtd_Pedida',
        'QTD_RECEBIDA_TOTAL': 'Qtd_Recebida', 'SALDO_A_COMPRAR': 'Saldo_A_Comprar',
        'RESIDUO': 'Residuo'
    }

    df_final = df_op.rename(columns=mapa_colunas)[list(mapa_colunas.values())]
    print(f"[3.5/4] Gerando Excel Operacional em: {EXCEL_OPERACIONAL_PATH}")
    df_final.to_excel(EXCEL_OPERACIONAL_PATH, index=False, engine='openpyxl')


if __name__ == "__main__":
    print("=== INICIANDO PIPELINE DE COMPRAS ===")
    baixar_dados_totvs()
    processar_dados()
    enviar_para_nuvem()
    print("=== PIPELINE FINALIZADO ===")