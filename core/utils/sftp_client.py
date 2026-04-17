from dotenv import load_dotenv
import paramiko
import os

import os
import paramiko
from dotenv import load_dotenv

load_dotenv()

SFTP_HOST = os.getenv('SFTP_HOST')
SFTP_PORT = int(os.getenv('SFTP_PORT', 1401))
SFTP_USER = os.getenv('SFTP_USER')
SFTP_PASS = os.getenv('SFTP_PASS')
SFTP_REMOTE_DIR = os.getenv('SFTP_REMOTE_DIR')


def baixar_arquivos_sftp(arquivos_alvo, diretorio_destino):
    """
    Função genérica para baixar arquivos via SFTP.
    :param arquivos_alvo: Lista de strings com os nomes dos arquivos (ex: ['sg1010.sdb'])
    :param diretorio_destino: Caminho completo de onde salvar os arquivos
    """
    os.makedirs(diretorio_destino, exist_ok=True)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print("[CORE] Conectando ao servidor TOTVS via SFTP...")
    try:
        ssh.connect(hostname=SFTP_HOST, port=SFTP_PORT, username=SFTP_USER, password=SFTP_PASS)
        sftp = ssh.open_sftp()
        sftp.chdir(SFTP_REMOTE_DIR)

        for arquivo in arquivos_alvo:
            print(f"[CORE] Baixando {arquivo}...")
            # Salva o arquivo no diretório de destino que quem chamou a função escolheu
            sftp.get(arquivo, os.path.join(diretorio_destino, arquivo))

        print("[CORE] Download concluído com sucesso.")
    except Exception as e:
        print(f"[ERRO CORE] Falha no SFTP: {e}")
        raise
    finally:
        if 'sftp' in locals(): sftp.close()
        ssh.close()