import tempfile
from decimal import Decimal

import pandas as pd
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from compras.services.pms_etl_service import ComprasPmsETLService
from compras.tasks import LOCK_SYNC_COMPRAS_PMS
from core.utils.sftp_client import dowload_files_sftp


class Command(BaseCommand):
    help = "Sincroniza dados PMS do Protheus para o dashboard financeiro de Compras."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Valida arquivos e schema PMS sem gravar dados no banco.',
        )

    def handle(self, *args, **options):
        if options['dry_run']:
            self._dry_run()
            return

        self.stdout.write("Iniciando sincronizacao PMS de Compras...")

        if not cache.add(LOCK_SYNC_COMPRAS_PMS, True, timeout=3600):
            raise CommandError("Sincronizacao PMS de Compras ja esta em andamento.")

        try:
            ComprasPmsETLService.executar()
        except Exception as exc:
            raise CommandError(
                f"Falha na sincronizacao PMS de Compras: {exc}"
            ) from exc
        finally:
            cache.delete(LOCK_SYNC_COMPRAS_PMS)

        self.stdout.write(self.style.SUCCESS("Sincronizacao PMS de Compras concluida."))

    def _dry_run(self):
        self.stdout.write("Iniciando validacao PMS em modo dry-run...")

        with tempfile.TemporaryDirectory() as tmpdirname:
            dowload_files_sftp(
                arquivos_alvo=ComprasPmsETLService.ARQUIVOS_ALVO,
                diretorio_destino=tmpdirname,
            )
            dados_limpos = ComprasPmsETLService._ler_e_limpar_arquivos(tmpdirname)

        ComprasPmsETLService._validar_schema(dados_limpos)

        projetos = ComprasPmsETLService._montar_projetos(dados_limpos.get('af8', pd.DataFrame()))
        edts = ComprasPmsETLService._montar_edts(dados_limpos.get('afc', pd.DataFrame()))
        tarefas = ComprasPmsETLService._montar_tarefas(dados_limpos.get('af9', pd.DataFrame()))
        custos = ComprasPmsETLService._montar_custos(
            df_tarefas=dados_limpos.get('af9', pd.DataFrame()),
            df_produtos=dados_limpos.get('afa', pd.DataFrame()),
            df_despesas=dados_limpos.get('afb', pd.DataFrame()),
            df_mapeamentos=dados_limpos.get('afg', pd.DataFrame()),
            df_pedidos=dados_limpos.get('sc7', pd.DataFrame()),
            df_recebimentos=dados_limpos.get('sd1', pd.DataFrame()),
        )
        custo_previsto = sum(
            (custo.custo_previsto for custo in custos),
            Decimal('0'),
        )
        custo_empenhado = sum(
            (custo.custo_empenhado for custo in custos),
            Decimal('0'),
        )
        custo_realizado = sum(
            (custo.custo_realizado for custo in custos),
            Decimal('0'),
        )

        self.stdout.write(self.style.SUCCESS("Dry-run PMS concluido sem gravar dados."))
        self.stdout.write(f"Arquivos: {', '.join(ComprasPmsETLService.ARQUIVOS_ALVO)}")
        self.stdout.write(f"Projetos: {len(projetos)}")
        self.stdout.write(f"EDTs: {len(edts)}")
        self.stdout.write(f"Tarefas: {len(tarefas)}")
        self.stdout.write(f"Custos por tarefa: {len(custos)}")
        self.stdout.write(f"Custo previsto: {custo_previsto:.2f}")
        self.stdout.write(f"Custo empenhado: {custo_empenhado:.2f}")
        self.stdout.write(f"Custo realizado: {custo_realizado:.2f}")
