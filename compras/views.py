import os
import csv
import json
from datetime import datetime
from dotenv import load_dotenv
from django.core.cache import cache
from celery.result import AsyncResult

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from core.decorators import exige_permissao

from .models import DataWarehouseCompras, OperacaoCompras
from django.views.decorators.http import require_POST

from .services import gerar_csv_operacoes_compras, gerar_csv_gerencial_compras
from .task import task_sincronizar_protheus

load_dotenv()

@login_required(login_url='/login/')
@exige_permissao(['compras'])
def dashboard_compras(request):

    # Captura de Filtros do GET
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    projeto_filtro = request.GET.get('projeto')
    tarefa_filtro = request.GET.get('tarefa')
    fornecedor_filtro = request.GET.get('nome_fornecedor')
    exportar_csv = request.GET.get('export_csv')

    # QuerySet Base (Apenas Efetivados)
    pedidos_efetivados = DataWarehouseCompras.objects.exclude(status='PENDENTE').filter(
        tarefa_cod__startswith='03'
    )
    # Aplicação de Filtros
    if projeto_filtro:
        pedidos_efetivados = pedidos_efetivados.filter(projeto_cod=projeto_filtro)
    if tarefa_filtro:
        pedidos_efetivados = pedidos_efetivados.filter(tarefa_cod=tarefa_filtro)
    if fornecedor_filtro:
        pedidos_efetivados = pedidos_efetivados.filter(nome_fornecedor=fornecedor_filtro)

    # Filtro de Datas (Otimizado via ORM)
    if data_inicio and data_fim:
        try:
            pedidos_efetivados = pedidos_efetivados.filter(emissao_pedido__range=(data_inicio, data_fim))
        except Exception as e:
            messages.warning(request, "Erro ao filtrar datas. Verifique o formato.")

    # Exportação CSV
    if exportar_csv == '1':
        return gerar_csv_gerencial_compras(pedidos_efetivados)


    # KPIs Principais
    spend_total = pedidos_efetivados.aggregate(total=Sum('valor_total'))['total'] or 0.0
    lead_time_compras = pedidos_efetivados.aggregate(media=Avg('leadtime_compras'))['media'] or 0.0

    # KPI de Backlog
    backlog_query = DataWarehouseCompras.objects.filter(status='PENDENTE')
    if projeto_filtro: backlog_query = backlog_query.filter(projeto_cod=projeto_filtro)
    if tarefa_filtro: backlog_query = backlog_query.filter(tarefa_cod=tarefa_filtro)
    if fornecedor_filtro: backlog_query = backlog_query.filter(nome_fornecedor=fornecedor_filtro)
    backlog_sc = backlog_query.count()

    pedidos_entregues = pedidos_efetivados.filter(status='ENTREGUE')
    atraso_medio_fornecedores = pedidos_entregues.aggregate(media=Avg('dias_atraso_entrega'))['media'] or 0.0

    # Gráfico Curva ABC
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

    tarefas_query = DataWarehouseCompras.objects.exclude(tarefa_cod='').filter(
        tarefa_cod__startswith='03'
    )
    if projeto_filtro: tarefas_query = tarefas_query.filter(projeto_cod=projeto_filtro)
    lista_tarefas = tarefas_query.values_list('tarefa_cod', flat=True).distinct().order_by('tarefa_cod')

    lista_fornecedor = DataWarehouseCompras.objects.exclude(nome_fornecedor='').values_list('nome_fornecedor', flat=True).distinct().order_by(
        'nome_fornecedor')

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
        'lista_tarefas': lista_tarefas,
        'lista_fornecedor': lista_fornecedor,
        'filtros': {
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'projeto': projeto_filtro,
            'tarefa': tarefa_filtro,
            'fornecedor': fornecedor_filtro
        }
    }

    return render(request, 'compras/dashboard.html', context)


@login_required(login_url='/login/')
@exige_permissao(['compras'])
def dashboard_operacional(request):
    """
    Dashboard focado na operação (Compradores).
    Traz os dados agregados da OperacaoCompras para acompanhamento de filas e parciais.
    """
    # Busca Base Ordenada (Garante paginação correta)
    operacoes = OperacaoCompras.objects.all().order_by('-emissao_sc', 'num_sc')

    # Captura de Parâmetros
    projeto_filtro = request.GET.get('projeto')
    status_filtro = request.GET.get('status')
    pedido_filtro = request.GET.get('pedido')
    nota_filtro = request.GET.get('nota')

    sc_filtro = request.GET.get('num_sc')
    fornecedor_filtro = request.GET.get('nome_fornecedor')
    exportar_csv = request.GET.get('export_csv')

    # Aplicação de Filtros
    if projeto_filtro: operacoes = operacoes.filter(projeto_cod=projeto_filtro)
    if status_filtro: operacoes = operacoes.filter(status_operacional=status_filtro)
    if pedido_filtro: operacoes = operacoes.filter(num_pedidos_vinculados=pedido_filtro)
    if nota_filtro: operacoes = operacoes.filter(notas_fiscais=nota_filtro)
    if sc_filtro: operacoes = operacoes.filter(num_sc=sc_filtro)
    if fornecedor_filtro: operacoes = operacoes.filter(nome_fornecedor__icontains=fornecedor_filtro)

    # Exportação CSV
    if exportar_csv == '1':
        return gerar_csv_operacoes_compras(operacoes)

    # KPIs
    kpis = {
        'pendentes_cotacao': operacoes.filter(status_operacional='PENDENTE COTAÇÃO').count(),
        'compras_parciais': operacoes.filter(status_operacional='COMPRA PARCIAL').count(),
        'entregas_parciais': operacoes.filter(status_operacional='ENTREGA PARCIAL').count(),
        'aguardando_entrega': operacoes.filter(status_operacional='AGUARDANDO ENTREGA').count(),
    }

    #  Listas do Filtro
    lista_projetos = OperacaoCompras.objects.exclude(projeto_cod='').values_list('projeto_cod', flat=True).distinct().order_by('projeto_cod')
    lista_status = OperacaoCompras.objects.exclude(status_operacional='').values_list('status_operacional', flat=True).distinct().order_by('status_operacional')

    # Paginação
    paginator = Paginator(operacoes, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_filtros = query_params.urlencode()

    context = {
        'operacoes': page_obj,
        'kpis': kpis,
        'lista_projetos': lista_projetos,
        'lista_status': lista_status,
        'url_filtros': url_filtros,
        'filtros': {
            'projeto': projeto_filtro, 'status': status_filtro, 'pedido': pedido_filtro,
            'nota': nota_filtro, 'num_sc': sc_filtro, 'nome_fornecedor': fornecedor_filtro,
        }
    }

    return render(request, 'compras/dashboard_operacional.html', context)


@login_required(login_url='/login/')
@exige_permissao(['compras'])
@require_POST
def atualizar_dados_dw(request):
    if cache.get('lock_sync_compras'):
        return JsonResponse({
            "status": "locked",
            "message": "Sincronização já em andamento."
        })

    cache.set('lock_sync_compras', True, timeout=600)

    # Dispara a task assíncrona
    task = task_sincronizar_protheus.delay()

    return JsonResponse({
        "status": "processing",
        "task_id": task.id,
        "message": "Sincronização iniciada em segundo plano."
    })


@login_required(login_url='/login/')
def checar_status_sync(request, task_id):
    """
    Rota chamada via AJAX pelo frontend para checar se o Celery terminou.
    """
    task_result = AsyncResult(task_id)
    return JsonResponse({
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    })
