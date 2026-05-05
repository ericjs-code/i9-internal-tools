import pandas as pd
from celery import shared_task
from datetime import datetime
from django.db import transaction
from django.core.cache import cache

from compras.models import DataWarehouseCompras, OperacaoCompras
from compras.scripts.sync_protheus import carregar_dados_brutos


@shared_task
def task_sincronizar_protheus():
    """
    Task executada em background pelo Celery Worker.
    Não bloqueia o servidor web.
    """
    try:
        from compras.scripts.sync_protheus import (
            extrair_dados_compras, processar_dados, processar_dados_operacionais
        )


        extrair_dados_compras()

        dados_brutos = carregar_dados_brutos()

        df_dw = processar_dados(dados_brutos)
        df_op = processar_dados_operacionais(dados_brutos)

        registros_dw = []

        def limpa_str(val):
            return str(val).strip() if pd.notna(val) else ''

        def limpa_num(val):
            return float(val) if pd.notna(val) else 0.0

        def limpa_int(val):
            return int(val) if pd.notna(val) else 0

        def limpa_data(val):
            val_str = str(val).strip()
            if val_str and val_str not in ['-', 'nan', 'NaT']:
                try:
                    return datetime.strptime(val_str, '%d/%m/%Y').date()
                except ValueError:
                    return None
            return None

        for index, row in df_dw.iterrows():
            registros_dw.append(DataWarehouseCompras(
                filial=limpa_str(row.get('Filial')),
                num_sc=limpa_str(row.get('Num_SC')),
                cod_produto=limpa_str(row.get('Cod_Produto')),
                descricao=limpa_str(row.get('Descricao')),
                projeto_cod=limpa_str(row.get('Projeto_Cod')),
                tarefa_cod=limpa_str(row.get('Tarefa_Cod')),
                num_pedido=limpa_str(row.get('Num_Pedido')),
                cod_fornecedor=limpa_str(row.get('Cod_Fornecedor')),
                nome_fornecedor=limpa_str(row.get('Nome_Fornecedor')),
                status=limpa_str(row.get('Status')),
                emissao_sc=limpa_data(row.get('Emissao_SC')),
                emissao_pedido=limpa_data(row.get('Emissao_Pedido')),
                data_prev_recebimento_fisico=limpa_data(row.get('Data_Prev_Recebimento_Fisico')),
                data_recebimento_real=limpa_data(row.get('Data_Recebimento_Real')),
                qtd_solicitada=limpa_num(row.get('Qtd_Solicitada')),
                qtd_pedido=limpa_num(row.get('Qtd_Pedido')),
                qtd_recebida=limpa_num(row.get('Qtd_Recebida')),
                valor_unitario=limpa_num(row.get('Valor_Unitario')),
                valor_total=limpa_num(row.get('Valor_Total')),
                leadtime_compras=limpa_int(row.get('LeadTime_Compras')),
                leadtime_fornecedor=limpa_int(row.get('LeadTime_Fornecedor')),
                dias_atraso_entrega=limpa_int(row.get('Dias_Atraso_Entrega'))
            ))

        registros_op = []

        for index, row in df_op.iterrows():
            registros_op.append(OperacaoCompras(
                filial=limpa_str(row.get('Filial')),
                num_sc=limpa_str(row.get('Num_SC')),
                item_sc=limpa_str(row.get('Item_SC')),
                cod_produto=limpa_str(row.get('Cod_Produto')),
                descricao=limpa_str(row.get('Descricao')),
                projeto_cod=limpa_str(row.get('Projeto_Cod')),
                tarefa_cod=limpa_str(row.get('Tarefa_Cod')),
                num_pedidos_vinculados=limpa_str(row.get('Num_Pedidos_Vinculados')),
                notas_fiscais=limpa_str(row.get('Notas_Fiscais')),
                nome_fornecedor=limpa_str(row.get('Nome_Fornecedor')),
                status_operacional=limpa_str(row.get('Status_Operacional')),
                emissao_sc=limpa_data(row.get('Emissao_SC')),
                emissao_ultimo_pedido=limpa_data(row.get('Emissao_Ultimo_Pedido')),
                previsao_entrega=limpa_data(row.get('Previsao_Entrega')),
                ultima_entrega_real=limpa_data(row.get('Ultima_Entrega_Real')),
                qtd_solicitada=limpa_num(row.get('Qtd_Solicitada')),
                qtd_pedida=limpa_num(row.get('Qtd_Pedida')),
                qtd_recebida=limpa_num(row.get('Qtd_Recebida')),
                saldo_a_comprar=limpa_num(row.get('Saldo_A_Comprar')),
                residuo=limpa_num(row.get('Residuo'))
            ))

        with transaction.atomic():
            DataWarehouseCompras.objects.all().delete()
            OperacaoCompras.objects.all().delete()

            DataWarehouseCompras.objects.bulk_create(registros_dw, batch_size=2000)
            OperacaoCompras.objects.bulk_create(registros_op, batch_size=2000)

        return "Sincronização concluída com sucesso."

    except Exception as e:
        raise e
    finally:
        cache.delete('lock_sync_compras')