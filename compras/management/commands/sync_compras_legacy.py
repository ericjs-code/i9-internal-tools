from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from compras.services.etl_service import ComprasETLService
from compras.tasks import LOCK_SYNC_COMPRAS


class Command(BaseCommand):
    help = "Sincroniza dados legados do Protheus para os fluxos operacionais de Compras."

    def handle(self, *args, **options):
        self.stdout.write("Iniciando sincronizacao legada de Compras...")

        if not cache.add(LOCK_SYNC_COMPRAS, True, timeout=3600):
            raise CommandError("Sincronizacao legada de Compras ja esta em andamento.")

        try:
            ComprasETLService.executar()
        except Exception as exc:
            raise CommandError(
                f"Falha na sincronizacao legada de Compras: {exc}"
            ) from exc
        finally:
            cache.delete(LOCK_SYNC_COMPRAS)

        self.stdout.write(
            self.style.SUCCESS("Sincronizacao legada de Compras concluida.")
        )
