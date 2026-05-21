import os
import sqlite3
import pandas as pd
import tempfile
from core.utils.sftp_client import dowload_files_sftp
import logging

logger = logging.getLogger(__name__)


class ProtheusBaseETL:
    """
    Classe Base Enterprise para extração de dados do Protheus.
    Aplica o padrão Template Method.
    """
    ARQUIVOS_ALVO = []

    @classmethod
    def executar(cls):
        """Orquestrador principal do ETL. (Não sobrescrever nas classes filhas)"""
        if not cls.ARQUIVOS_ALVO:
            raise ValueError("As classes filhas precisam definir a lista ARQUIVOS_ALVO.")

        # tempfile garante que nada fique sujando o disco do servidor após a execução
        with tempfile.TemporaryDirectory() as tmpdirname:
            logger.info(f"[{cls.__name__}] Iniciando ETL. Diretório temporário: {tmpdirname}")

            # 1. Extração
            logger.info(f"[{cls.__name__}] Baixando arquivos via SFTP...")
            dowload_files_sftp(arquivos_alvo=cls.ARQUIVOS_ALVO, diretorio_destino=tmpdirname)

            # 2. Leitura e Transformação Base
            logger.info(f"[{cls.__name__}] Lendo e sanitizando bancos SDB...")
            dados_brutos = cls._ler_e_limpar_arquivos(tmpdirname)

            # 3. Transformação Específica do Domínio (Delega para as filhas)
            logger.info(f"[{cls.__name__}] Executando regra de negócio do módulo...")
            return cls.transformar_e_salvar(dados_brutos)

    @classmethod
    def _ler_e_limpar_arquivos(cls, diretorio) -> dict:
        """Lê os arquivos SQLite, decodifica Latin1 e remove deletados."""
        dados = {}

        for arquivo in cls.ARQUIVOS_ALVO:
            caminho = os.path.join(diretorio, arquivo)
            chave = arquivo[:3].lower()  # ex: 'sc1'

            if not os.path.exists(caminho):
                logger.error(f"Arquivo não encontrado no SFTP: {arquivo}")
                raise FileNotFoundError(f"CRÍTICO: O arquivo {arquivo} não foi encontrado no servidor.")

            # Conexão SQLite
            con = sqlite3.connect(caminho)
            con.text_factory = bytes
            cursor = con.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")

            # Alguns arquivos podem estar vazios ou não ter tabela padrão
            row = cursor.fetchone()
            if not row:
                logger.warning(f"O arquivo {arquivo} não possui tabelas válidas. Ignorando.")
                con.close()
                continue

            table_name = row[0].decode('latin1', errors='ignore')
            df = pd.read_sql(f"SELECT * FROM {table_name}", con)
            con.close()

            # Decodificação de Bytes
            def clean_bytes(valor):
                return valor.decode('latin1', errors='ignore') if isinstance(valor, bytes) else valor

            df = df.map(clean_bytes) if hasattr(df, 'map') else df.applymap(clean_bytes)
            df.columns = df.columns.str.strip().str.upper()

            # Limpeza Padrão Protheus (Diretamente no df atual)
            if 'D_E_L_E_T_' in df.columns:
                df.drop(df[df['D_E_L_E_T_'] == '*'].index, inplace=True)

            colunas_remover = [c for c in ['D_E_L_E_T_', 'R_E_C_N_O_', 'R_E_C_D_E_L_'] if c in df.columns]
            df.drop(columns=colunas_remover, inplace=True, errors='ignore')

            # Strip apenas nas colunas de texto para evitar erros e poupar CPU
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].str.strip()

            dados[chave] = df
            logger.debug(f"Arquivo {arquivo} lido com sucesso: {len(df)} linhas.")

        return dados

    @classmethod
    def transformar_e_salvar(cls, dados_limpos: dict):
        """Método Abstrato para ser implementado pelos módulos."""
        raise NotImplementedError(f"A classe {cls.__name__} deve implementar 'transformar_e_salvar()'")