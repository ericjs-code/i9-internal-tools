import csv
from django.http import HttpResponse
from core.utils.utils import formata_dt


def _configurar_response(filename):
    """Auxiliar privado para padronizar o cabeçalho HTTP"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(u'\ufeff'.encode('utf8'))  # BOM para Excel
    return response


def gerar_csv_operacoes_compras(queryset):
    response = _configurar_response("fila_operacional_compras.csv")
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'SC', 'Item', 'Produto', 'Descricao', 'Projeto', 'Tarefa',
        'Fornecedor', 'Status', 'Emissao SC',
        'Qtd Solicitada', 'Qtd Comprada', 'Qtd Entregue', 'Resíduo'
    ])

    for op in queryset:
        writer.writerow([
            op.num_sc, op.item_sc, op.cod_produto, op.descricao, op.projeto_cod, op.tarefa_cod,
            op.nome_fornecedor, op.status_operacional, formata_dt(op.emissao_sc),
            op.qtd_solicitada, op.qtd_pedida, op.qtd_recebida, op.residuo
        ])
    return response


def gerar_csv_gerencial_compras(queryset):
    response = _configurar_response("base_completa_compras.csv")
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'Filial', 'Num_SC', 'Emissao_SC', 'Cod_Produto', 'Descricao',
        'Projeto_Cod', 'Tarefa_Cod', 'Num_Pedido', 'Emissao_Pedido',
        'Data_Prev_Recebimento_Fisico', 'Data_Recebimento_Real', 'Cod_Fornecedor',
        'Nome_Fornecedor', 'Status', 'Qtd_Solicitada', 'Qtd_Pedido', 'Qtd_Recebida',
        'Valor_Unitario', 'Valor_Total', 'LeadTime_Compras',
        'LeadTime_Fornecedor', 'Dias_Atraso_Entrega'
    ])

    for obj in queryset:
        writer.writerow([
            obj.filial, obj.num_sc, formata_dt(obj.emissao_sc), obj.cod_produto, obj.descricao,
            obj.projeto_cod, obj.tarefa_cod, obj.num_pedido, formata_dt(obj.emissao_pedido),
            formata_dt(obj.data_prev_recebimento_fisico), formata_dt(obj.data_recebimento_real),
            obj.cod_fornecedor, obj.nome_fornecedor, obj.status, obj.qtd_solicitada,
            obj.qtd_pedido, obj.qtd_recebida, obj.valor_unitario, obj.valor_total,
            obj.leadtime_compras, obj.leadtime_fornecedor, obj.dias_atraso_entrega
        ])
    return response