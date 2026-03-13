import pandas as pd
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Avg, Count, F, Q
from .models import DataWarehouseCompras


@csrf_exempt
def api_upload_compras(request):
    """
    API Recebedora: Lê o Excel enviado pelo script local e popula o DW.
    """
    if request.method == 'POST' and request.FILES.get('arquivo'):

        token = request.headers.get('X-Api-Key')
        if token != 'l_^e1#ye7@wro)4@gti24vxcmrr$01(@sxdp@=qg40(^vkvwzr':
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

@login_required(login_url='/login/')
def dashboard_compras(request):
    if not (request.user.is_superuser or getattr(request.user, 'is_compras', False) or getattr(request.user,'is_diretoria', False) or getattr(
            request.user, 'is_ti', False)):
        messages.error(request, "Acesso restrito à Diretoria e equipe de Compras.")
        return redirect('home')

    pedidos_efetivados = DataWarehouseCompras.objects.exclude(status='Pendente')

    spend_total = pedidos_efetivados.aggregate(total=Sum('valor_total'))['total'] or 0.0

    curva_abc_projetos = pedidos_efetivados.exclude(projeto_cod='').values('projeto_cod').annotate(
        custo_total=Sum('valor_total')
    ).order_by('-custo_total')[:5]


    lead_time_compras = pedidos_efetivados.aggregate(media=Avg('leadtime_compras'))['media'] or 0.0

    backlog_sc = DataWarehouseCompras.objects.filter(status='PENDENTE').count()

    pedidos_entregues = DataWarehouseCompras.objects.filter(status='ENTREGUE')

    atraso_medio_fornecedores = pedidos_entregues.aggregate(media=Avg('dias_atraso_entrega'))['media'] or 0.0

    piores_fornecedores = pedidos_entregues.exclude(nome_fornecedor='').values('nome_fornecedor').annotate(
        media_atraso=Avg('dias_atraso_entrega'),
        volume_pedidos=Count('id')
    ).filter(volume_pedidos__gte=3).order_by('-media_atraso')[:5]

    projetos_labels = [p['projeto_cod'] for p in curva_abc_projetos]
    projetos_data = [float(p['custo_total']) for p in curva_abc_projetos]

    fornecedores_labels = [f['nome_fornecedor'][:15] + '...' if len(f['nome_fornecedor']) > 15 else f['nome_fornecedor'] for f in piores_fornecedores]
    fornecedores_data = [float(f['media_atraso']) for f in piores_fornecedores]

    context = {
        'spend_total': spend_total,
        'lead_time_compras': round(lead_time_compras, 1),
        'backlog_sc': backlog_sc,
        'atraso_medio_fornecedores': round(atraso_medio_fornecedores, 1),

        'projetos_labels': projetos_labels,
        'projetos_data': projetos_data,
        'fornecedores_labels': fornecedores_labels,
        'fornecedores_data': fornecedores_data,
    }

    return render(request, 'compras/dashboard.html', context)