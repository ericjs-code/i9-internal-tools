import os
import pandas as pd
import numpy as np
import sqlite3
from core.utils.sftp_client import dowload_files_sftp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Arquivos Corrigidos
ARQUIVOS_COMPRAS = [
    'sc101011.sdb', 'sc701011.sdb',
    'sa20101.sdb', 'sd10101.sdb', 'afg0101.sdb',
    'sb10101.sdb', 'sx50101.sdb'
]

def extrair_dados_compras():
    dowload_files_sftp(arquivos_alvo=ARQUIVOS_COMPRAS, diretorio_destino=DATA_DIR)

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

def carregar_dados_brutos():
    """Lê do disco apenas UMA VEZ e devolve os dados crus na RAM"""
    print("[ETL] Lendo arquivos SDB para a memória...")
    return {

        'sc1': ler_tabela_sqlite('sc10101.sdb'),
        'sc7': ler_tabela_sqlite('sc70101.sdb'),
        'sa2': ler_tabela_sqlite('sa20101.sdb'),
        'sd1': ler_tabela_sqlite('sd10101.sdb'),
        'afg': ler_tabela_sqlite('afg0101.sdb'),
        'sb1': ler_tabela_sqlite('sb10101.sdb'),
        'sx5': ler_tabela_sqlite('sx50101.sdb'),
    }


def processar_dados(dados_brutos):
    """ Processamento do Dashboard Gerencial (DW) """
    print("[2/4] Processando e limpando dados (ETL DW)...")

    df_sc1 = dados_brutos['sc1'].copy()
    df_sc7 = dados_brutos['sc7'].copy()
    df_sa2 = dados_brutos['sa2'].copy()
    df_sd1 = dados_brutos['sd1'].copy()
    df_afg = dados_brutos['afg'].copy()

    for df in [df_sc1, df_sc7, df_sa2, df_sd1, df_afg]:
        if 'D_E_L_E_T_' in df.columns:
            df.drop(df[df['D_E_L_E_T_'] == '*'].index, inplace=True)
        colunas_remover = [c for c in ['D_E_L_E_T_', 'R_E_C_N_O_', 'R_E_C_D_E_L_'] if c in df.columns]
        df.drop(columns=colunas_remover, inplace=True, errors='ignore')
        for col in df.columns:
            df[col] = df[col].str.strip()

    df_sd1['D1_QUANT'] = pd.to_numeric(df_sd1['D1_QUANT'], errors='coerce').fillna(0)
    df_sd1_agg = df_sd1.groupby(['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC']).agg(
        QTD_RECEBIDA=('D1_QUANT', 'sum'),
        DATA_RECEBIMENTO_REAL=('D1_DTDIGIT', 'max')
    ).reset_index()

    # Blindagem de Fornecedor DW
    df_sa2_unico = df_sa2.drop_duplicates(subset=['A2_COD']).copy()
    df_sa2_unico['A2_COD'] = df_sa2_unico['A2_COD'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(6)

    if 'AFG_NUMSC' in df_afg.columns:
        df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC'])
    else:
        df_afg_unique = pd.DataFrame(columns=['AFG_NUMSC', 'AFG_ITEMSC', 'AFG_PROJET', 'AFG_TAREFA'])

    df_merged = pd.merge(df_sc1, df_sc7, how='left', left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'], right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])
    df_merged = pd.merge(df_merged, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'], right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
    df_merged['PROJETO_CODIGO'] = df_merged.get('AFG_PROJET', '')
    df_merged['TAREFA_CODIGO'] = df_merged.get('AFG_TAREFA', '')

    # Cruzamento Blindado
    df_merged['C7_FORNECE'] = df_merged['C7_FORNECE'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(6)
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
    cols_finais = list(colunas_map.values()) + ['Emissao_SC', 'Emissao_Pedido', 'Data_Prev_Recebimento_Fisico', 'Data_Recebimento_Real']
    df_final = df_final[[c for c in cols_finais if c in df_final.columns]]

    for col in ['Qtd_Solicitada', 'Qtd_Pedido', 'Qtd_Recebida', 'Valor_Unitario', 'Valor_Total']:
        if col in df_final.columns:
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0)

    print("[3/4] Retornando dados do DW para a memória...")
    return df_final


def processar_dados_operacionais(dados_brutos):
    """ Processamento da Tabela Operacional (Avaliações) """
    print('[ETL OPERACIONAL] Processando base bottom-up...')

    df_sc1 = dados_brutos['sc1'].copy()
    df_sc7 = dados_brutos['sc7'].copy()
    df_sa2 = dados_brutos['sa2'].copy()
    df_sd1 = dados_brutos['sd1'].copy()
    df_afg = dados_brutos['afg'].copy()
    df_sb1 = dados_brutos['sb1'].copy()
    df_sx5 = dados_brutos['sx5'].copy()

    for df in [df_sc1, df_sc7, df_sa2, df_sd1, df_afg, df_sb1, df_sx5]:
        if 'D_E_L_E_T_' in df.columns:
            df.drop(df[df['D_E_L_E_T_'] == '*'].index, inplace=True)
        colunas_remover = [c for c in ['D_E_L_E_T_', 'R_E_C_N_O_', 'R_E_C_D_E_L_'] if c in df.columns]
        df.drop(columns=colunas_remover, inplace=True, errors='ignore')
        for col in df.columns:
            df[col] = df[col].str.strip()

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

    df_sc7_sd1 = pd.merge(df_sc7, df_sd1_agg, how='left', left_on=['C7_FILIAL', 'C7_NUM', 'C7_ITEM'], right_on=['D1_FILIAL', 'D1_PEDIDO', 'D1_ITEMPC'])
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
        TIPO_PRODUTO=('X5_DESCRI', lambda x: ', '.join([str(i).strip() for i in x.dropna().unique() if str(i).strip() != '']))
    ).reset_index()

    df_op = pd.merge(df_sc1, df_sc7_agg, how='left', left_on=['C1_FILIAL', 'C1_NUM', 'C1_ITEM'], right_on=['C7_FILIAL', 'C7_NUMSC', 'C7_ITEMSC'])

    df_op['QTD_PEDIDA_TOTAL'] = df_op['QTD_PEDIDA_TOTAL'].fillna(0).round(3)
    df_op['QTD_RECEBIDA_TOTAL'] = df_op['QTD_RECEBIDA_TOTAL'].fillna(0).round(3)
    df_op['VALOR_RECEBIDO_TOTAL'] = df_op['VALOR_RECEBIDO_TOTAL'].fillna(0)

    # Limpeza Blindada do Fornecedor Operacional
    df_sa2_mini = df_sa2.drop_duplicates(subset=['A2_COD'])[['A2_COD', 'A2_NOME', 'A2_CGC']].copy()
    df_op['COD_FORNECEDOR'] = df_op['COD_FORNECEDOR'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(6)
    df_sa2_mini['A2_COD'] = df_sa2_mini['A2_COD'].astype(str).str.split('.').str[0].str.replace(r'\D', '', regex=True).str.zfill(6)

    df_op = pd.merge(df_op, df_sa2_mini, how='left', left_on='COD_FORNECEDOR', right_on='A2_COD')
    df_op['NOME_FORNECEDOR_FINAL'] = df_op['A2_NOME'].fillna('FORNECEDOR NÃO ENCONTRADO')

    if 'AFG_NUMSC' in df_afg.columns:
        df_afg_unique = df_afg.drop_duplicates(subset=['AFG_NUMSC', 'AFG_ITEMSC']).copy()
        df_op = pd.merge(df_op, df_afg_unique, how='left', left_on=['C1_NUM', 'C1_ITEM'], right_on=['AFG_NUMSC', 'AFG_ITEMSC'])
        df_op['PROJETO_CODIGO'] = df_op['AFG_PROJET']
    else:
        df_op['PROJETO_CODIGO'], df_op['AFG_TAREFA'] = '', ''

    df_op['SALDO_A_COMPRAR'] = (df_op['C1_QUANT'] - df_op['QTD_PEDIDA_TOTAL']).clip(lower=0)
    df_op['RESIDUO'] = (df_op['C1_QUANT'] - df_op['QTD_PEDIDA_TOTAL']).clip(lower=0).round(3)

    condicoes = [
        (df_op['QTD_PEDIDA_TOTAL'] == 0),
        (df_op['QTD_PEDIDA_TOTAL'] < df_op['C1_QUANT']) & (df_op['QTD_PEDIDA_TOTAL'] > 0),
        (df_op['QTD_PEDIDA_TOTAL'] >= df_op['C1_QUANT']) & (df_op['QTD_RECEBIDA_TOTAL'] == 0),
        (df_op['QTD_PEDIDA_TOTAL'] >= df_op['C1_QUANT']) & (df_op['QTD_RECEBIDA_TOTAL'] > 0) & (df_op['QTD_RECEBIDA_TOTAL'] < df_op['QTD_PEDIDA_TOTAL']),
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
    print("[3.5/4] Retornando dados Operacionais para a memória...")
    return df_final