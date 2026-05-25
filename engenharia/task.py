from celery import shared_task
from django.core.cache import cache
import logging
from engenharia.services.etl_service import EngenhariaETLService

logger = logging.getLogger(__name__)

@shared_task
def task_sincronizar_protheus():
    """
    Orquestrador em background.
    Apenas garante o lock de concorrência e chama o Service.
    """

    logger.info("[CELERY] Iniciando Task Sincronização Engenharia...")

    try:
        EngenhariaETLService.executar()

        logger.info("[CELERY] Task Sincronização Engenharia finalizada com sucesso.")
        return "Sincronização concluída com sucesso."

    except Exception as e:
        logger.error(f"[CELERY] Erro crítico na sincronização da Engenharia: {e}")
        raise e
    finally:
        # O Lock do Upstash é liberado independentemente de sucesso ou falha
        cache.delete('lock_sync_engenharia')
