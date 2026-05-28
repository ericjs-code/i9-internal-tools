import logging
from celery import shared_task
from .services import PCPEstoqueETLService

logger = logging.getLogger(__name__)

@shared_task(name="pcp.run_pcp_estoque_etl")
def run_pcp_estoque_etl():
    """
    Executa a extração, transformação e carga das movimentações
    de estoque do Protheus (SD1, SD2, SD3) para o Data Mart do PCP.
    """
    logger.info("Iniciando task Celery: pcp.run_pcp_estoque_etl")
    
    try:
        # A classe herda de ProtheusBaseETL, então o método orquestrador é o executar()
        PCPEstoqueETLService.executar()
        logger.info("Task pcp.run_pcp_estoque_etl finalizada com sucesso.")
    except Exception as e:
        logger.error(f"Erro na execução da task pcp.run_pcp_estoque_etl: {str(e)}", exc_info=True)
        raise e
