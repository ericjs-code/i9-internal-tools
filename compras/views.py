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


import csv
import json
from datetime import datetime
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Avg, Count, Q
from .models import DataWarehouseCompras


@login_required(login_url='/login/')
def dashboard_compras(request):
    if not (request.user.is_superuser or getattr(request.user, 'is_compras', False) or getattr(request.user, 'is_diretoria', False) or getattr(
            request.user, 'is_ti', False)):
        messages.error(request, "Acesso restrito à Diretoria e equipe de Compras.")
        return redirect('home')

    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    projeto_filtro = request.GET.get('projeto')
    exportar_csv = request.GET.get('export_csv')

    pedidos_efetivados = DataWarehouseCompras.objects.exclude(status='PENDENTE')

    if projeto_filtro:
        pedidos_efetivados = pedidos_efetivados.filter(projeto_cod=projeto_filtro)

    if data_inicio and data_fim:
        try:
            dt_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            dt_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()

            ids_validos = []
            for ped in pedidos_efetivados:
                if ped.emissao_pedido and ped.emissao_pedido != '-':
                    dt_ped = datetime.strptime(ped.emissao_pedido, '%d/%m/%Y').date()
                    if dt_inicio <= dt_ped <= dt_fim:
                        ids_validos.append(ped.id)

            pedidos_efetivados = pedidos_efetivados.filter(id__in=ids_validos)
        except Exception as e:
            messages.warning(request, "Erro ao filtrar datas. Verifique o formato.")

    if exportar_csv == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="extracao_compras.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')
        writer.writerow(
            ['Num_SC', 'Num_Pedido', 'Emissão', 'Projeto', 'Tarefa', 'Fornecedor', 'Status', 'Qtd', 'Valor_Unit',
             'Valor_Total'])

        for obj in pedidos_efetivados:
            writer.writerow([
                obj.num_sc, obj.num_pedido, obj.emissao_pedido, obj.projeto_cod, obj.tarefa_cod,
                obj.nome_fornecedor, obj.status, obj.qtd_pedido, obj.valor_unitario, obj.valor_total
            ])
        return response

    spend_total = pedidos_efetivados.aggregate(total=Sum('valor_total'))['total'] or 0.0
    lead_time_compras = pedidos_efetivados.aggregate(media=Avg('leadtime_compras'))['media'] or 0.0

    backlog_query = DataWarehouseCompras.objects.filter(status='PENDENTE')
    if projeto_filtro: backlog_query = backlog_query.filter(projeto_cod=projeto_filtro)
    backlog_sc = backlog_query.count()

    pedidos_entregues = pedidos_efetivados.filter(status='ENTREGUE')
    atraso_medio_fornecedores = pedidos_entregues.aggregate(media=Avg('dias_atraso_entrega'))['media'] or 0.0

    curva_abc_projetos = pedidos_efetivados.exclude(projeto_cod='').values('projeto_cod').annotate(
        custo_total=Sum('valor_total')
    ).order_by('-custo_total')[:5]

    projetos_labels = [p['projeto_cod'] for p in curva_abc_projetos]
    projetos_data = [float(p['custo_total']) for p in curva_abc_projetos]

    drilldown_dict = {}
    for p in curva_abc_projetos:
        cod_proj = p['projeto_cod']
        tarefas = pedidos_efetivados.filter(projeto_cod=cod_proj).exclude(tarefa_cod='').values('tarefa_cod').annotate(
            custo_tarefa=Sum('valor_total')
        ).order_by('-custo_tarefa')

        drilldown_dict[cod_proj] = {
            'labels': [t['tarefa_cod'] for t in tarefas],
            'data': [float(t['custo_tarefa']) for t in tarefas]
        }

    piores_fornecedores = pedidos_entregues.exclude(nome_fornecedor='').values('nome_fornecedor').annotate(
        media_atraso=Avg('dias_atraso_entrega'),
        volume=Count('id')
    ).filter(volume__gte=3).order_by('-media_atraso')[:5]

    fornecedores_labels = [f['nome_fornecedor'][:15] + '...' if len(f['nome_fornecedor']) > 15 else f['nome_fornecedor']
                           for f in piores_fornecedores]
    fornecedores_data = [float(f['media_atraso']) for f in piores_fornecedores]

    lista_projetos = DataWarehouseCompras.objects.exclude(projeto_cod='').values_list('projeto_cod',
                                                                                      flat=True).distinct().order_by(
        'projeto_cod')

    context = {
        'spend_total': spend_total,
        'lead_time_compras': round(lead_time_compras, 1),
        'backlog_sc': backlog_sc,
        'atraso_medio_fornecedores': round(atraso_medio_fornecedores, 1),

        'projetos_labels': json.dumps(projetos_labels),
        'projetos_data': json.dumps(projetos_data),
        'drilldown_dict': json.dumps(drilldown_dict),

        'fornecedores_labels': json.dumps(fornecedores_labels),
        'fornecedores_data': json.dumps(fornecedores_data),

        'lista_projetos': lista_projetos,
        'filtros': {'data_inicio': data_inicio, 'data_fim': data_fim, 'projeto': projeto_filtro}
    }

    return render(request, 'compras/dashboard.html', context)