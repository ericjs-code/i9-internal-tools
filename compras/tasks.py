import logging

from celery import shared_task
from django.core.cache import cache

from compras.services.etl_service import ComprasETLService
from compras.services.pms_etl_service import ComprasPmsETLService


logger = logging.getLogger(__name__)
LOCK_SYNC_COMPRAS = 'lock_sync_compras'
LOCK_SYNC_COMPRAS_PMS = 'lock_sync_compras_pms'


@shared_task
def task_sincronizar_protheus():
    """
    Orquestrador em background.
    Apenas garante o lock de concorrência e chama o Service.
    """
    logger.info("[CELERY] Iniciando Task Sincronização Compras...")

    try:
        ComprasETLService.executar()

        logger.info("[CELERY] Task Sincronização Compras finalizada com sucesso.")
        return "Sincronização concluída com sucesso."

    except Exception as e:
        logger.error(f"[CELERY] Erro crítico na sincronização de Compras: {e}")
        raise e
    finally:
        # O Lock do Upstash é liberado independentemente de sucesso ou falha
        cache.delete(LOCK_SYNC_COMPRAS)


@shared_task
def task_sincronizar_pms_protheus():
    """
    Sincroniza dados PMS para o dashboard financeiro de Compras.
    Usa lock separado do fluxo legado para evitar interferência entre cargas.
    """
    logger.info("[CELERY] Iniciando Task Sincronização PMS Compras...")

    try:
        ComprasPmsETLService.executar()

        logger.info("[CELERY] Task Sincronização PMS Compras finalizada com sucesso.")
        return "Sincronização PMS concluída com sucesso."

    except Exception as e:
        logger.error(f"[CELERY] Erro crítico na sincronização PMS de Compras: {e}")
        raise e
    finally:
        cache.delete(LOCK_SYNC_COMPRAS_PMS)
