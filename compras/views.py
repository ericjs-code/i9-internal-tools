import pandas as pd
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import DataWarehouseCompras


@csrf_exempt
def api_upload_compras(request):
    """
    API Recebedora: Lê o Excel enviado pelo script local e popula o DW.
    """
    if request.method == 'POST' and request.FILES.get('arquivo'):

        token = request.headers.get('X-Api-Key')
        if token != 'I9TMG_CHAVE_SECRETA_2026':
            return JsonResponse({'erro': 'Acesso negado. Token inválido.'}, status=403)

        arquivo = request.FILES['arquivo']

        try:
            df = pd.read_excel(arquivo)

            DataWarehouseCompras.objects.all().delete()

            registros = []
            for index, row in df.iterrows():
                def limpa_str(val): return str(val).strip() if pd.notna(val) else ''

                def limpa_num(val): return float(val) if pd.notna(val) else 0.0

                def limpa_int(val): return int(val) if pd.notna(val) else 0

                registros.append(
                    DataWarehouseCompras(
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
                        emissao_sc=limpa_str(row.get('Emissao_SC')),
                        emissao_pedido=limpa_str(row.get('Emissao_Pedido')),
                        data_prev_recebimento_fisico=limpa_str(row.get('Data_Prev_Recebimento_Fisico')),
                        data_recebimento_real=limpa_str(row.get('Data_Recebimento_Real')),
                        qtd_solicitada=limpa_num(row.get('Qtd_Solicitada')),
                        qtd_pedido=limpa_num(row.get('Qtd_Pedido')),
                        qtd_recebida=limpa_num(row.get('Qtd_Recebida')),
                        valor_unitario=limpa_num(row.get('Valor_Unitario')),
                        valor_total=limpa_num(row.get('Valor_Total')),
                        leadtime_compras=limpa_int(row.get('LeadTime_Compras')),
                        leadtime_fornecedor=limpa_int(row.get('LeadTime_Fornecedor')),
                        dias_atraso_entrega=limpa_int(row.get('Dias_Atraso_Entrega'))
                    )
                )

            DataWarehouseCompras.objects.bulk_create(registros, batch_size=2000)

            return JsonResponse({'mensagem': f'Carga concluída: {len(registros)} registros sincronizados.'}, status=200)

        except Exception as e:
            return JsonResponse({'erro': f'Falha no processamento: {str(e)}'}, status=500)

    return JsonResponse({'erro': 'Requisição inválida ou sem arquivo.'}, status=400)