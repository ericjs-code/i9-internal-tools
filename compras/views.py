import os
import csv
import json
from datetime import datetime
from dotenv import load_dotenv

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from core.decorators import exige_permissao

from .models import DataWarehouseCompras, OperacaoCompras
from .scripts.sync_protheus import extrair_dados_compras

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
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="base_completa_compras.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Filial', 'Num_SC', 'Emissao_SC', 'Cod_Produto', 'Descricao',
            'Projeto_Cod', 'Tarefa_Cod', 'Num_Pedido', 'Emissao_Pedido',
            'Data_Prev_Recebimento_Fisico', 'Data_Recebimento_Real', 'Cod_Fornecedor',
            'Nome_Fornecedor', 'Status', 'Qtd_Solicitada', 'Qtd_Pedido', 'Qtd_Recebida',
            'Valor_Unitario', 'Valor_Total', 'LeadTime_Compras',
            'LeadTime_Fornecedor', 'Dias_Atraso_Entrega'
        ])

        def formata_dt(data_obj):
            return data_obj.strftime('%d/%m/%Y') if data_obj else '-'

        for obj in pedidos_efetivados:
            writer.writerow([
                obj.filial, obj.num_sc, formata_dt(obj.emissao_sc), obj.cod_produto, obj.descricao,
                obj.projeto_cod, obj.tarefa_cod, obj.num_pedido, formata_dt(obj.emissao_pedido),
                formata_dt(obj.data_prev_recebimento_fisico), formata_dt(obj.data_recebimento_real),
                obj.cod_fornecedor, obj.nome_fornecedor, obj.status, obj.qtd_solicitada,
                obj.qtd_pedido, obj.qtd_recebida, obj.valor_unitario, obj.valor_total,
                obj.leadtime_compras, obj.leadtime_fornecedor, obj.dias_atraso_entrega
            ])
        return response

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
def atualizar_dados_dw(request):
    """
    View acionada pelo botão do Dashboard.
    Executa os scripts de ETL e salva nos DOIS bancos de dados (Diretoria e Operação).
    """

    try:
        # Importa os robôs e os caminhos
        from compras.scripts.sync_protheus import (
            extrair_dados_compras, processar_dados, processar_dados_operacionais,
            EXCEL_PATH, EXCEL_OPERACIONAL_PATH
        )

        # Executa a extração e as DUAS transformações
        extrair_dados_compras()
        processar_dados()
        processar_dados_operacionais()

        df_dw = pd.read_excel(EXCEL_PATH)
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


        df_op = pd.read_excel(EXCEL_OPERACIONAL_PATH)
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

        # Injeção no Banco de Dados com Transação Atômica (O Maestro)
        with transaction.atomic():
            # Limpa as duas gavetas
            DataWarehouseCompras.objects.all().delete()
            OperacaoCompras.objects.all().delete()

            # Preenche as duas gavetas
            DataWarehouseCompras.objects.bulk_create(registros_dw, batch_size=2000)
            OperacaoCompras.objects.bulk_create(registros_op, batch_size=2000)

        messages.success(request,
                         f"Sincronização concluída! Diretoria: {len(registros_dw)} | Operação: {len(registros_op)} registros atualizados.")

    except Exception as e:
        messages.error(request, f"Falha na sincronização: {str(e)}")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    else:
        return redirect('dashboard_compras')


@login_required(login_url='/login/')
@exige_permissao(['compras'])
def dashboard_operacional(request):
    """Dashboard focado na operação compras"""
    # Busca todos os dados operacionais
    operacoes = OperacaoCompras.objects.all()

    # Filtros simples
    projeto_filtros = request.GET.get('projeto')
    status_filtro = request.GET.get('status')

    if projeto_filtros:
        operacoes = operacoes.filter(projeto_cod=projeto_filtros)
    if status_filtro:
        operacoes = operacoes.filter(status_operacional=status_filtro)

    # KPIS
    kpis = {
        'pendentes_cotação': operacoes.filter(status_operacional='PENDENTE_COTAÇÃO'),
        'compras_parciais': operacoes.filter(status_operacional='COMPRAS_PARCIAIS'),
        'entregas_parciais': operacoes.filter(status_operacional= 'ENTREGA PARCIAL'),
        'aguardando_entrega': operacoes.filter(status_operacional='AGUARDANDO_ENTREGA')
    }

    lista_projetos = OperacaoCompras.objects.exclude(projeto_cod='').values_list('projeto_cod', flat=True).distinct().order_by('projeto_cod')
    lista_status = OperacaoCompras.objects.exclude(status_operacional='').values_list('status_operacional',flat=True).distinct().order_by('status_operacional')


    context = {
        'operacoes': operacoes,
        'kpis': kpis,
        'lista_projetos': lista_projetos,
        'lista_status': lista_status,
    }

    """
    Dashboard focado na operação (Compradores).
    Traz os dados agregados da OperacaoCompras para acompanhamento de filas e parciais.
    """

    # Busca
    operacoes = OperacaoCompras.objects.all()

    # Filtros
    projeto_filtro = request.GET.get('projeto')
    status_filtro = request.GET.get('status')
    pedido_filtro = request.GET.get('pedido')
    nota_filtro = request.GET.get('nota')
    sc_filtro = request.GET.get('num_sc')
    fornecedor_filtro = request.GET.get('nome_fornecedor')
    exportar_csv = request.GET.get('export_csv')

    if projeto_filtro:
        operacoes = operacoes.filter(projeto_cod=projeto_filtro)
    if status_filtro:
        operacoes = operacoes.filter(status_operacional=status_filtro)
    if pedido_filtro:
        operacoes = operacoes.filter(num_pedidos_vinculados=pedido_filtro)
    if nota_filtro:
        operacoes = operacoes.filter(notas_fiscais=nota_filtro)
    if sc_filtro:
        operacoes = operacoes.filter(num_sc=sc_filtro)
    if fornecedor_filtro:
        operacoes = operacoes.filter(nome_fornecedor__icontains=fornecedor_filtro)

    if exportar_csv == '1':
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="fila_operacional_compras.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')

        # Cabeçalho do Excel
        writer.writerow([
            'SC', 'Item', 'Produto', 'Descricao', 'Projeto', 'Tarefa',
            'Fornecedor', 'Status',
            'Emissao SC',
            'Qtd Solicitada', 'Qtd Comprada', 'Qtd Entregue', 'Resíduo'
        ])

        def formata_dt(data_obj):
            return data_obj.strftime('%d/%m/%Y') if data_obj else '-'

        # Linhas de Dados
        for op in operacoes:
            writer.writerow([
                op.num_sc, op.item_sc, op.cod_produto, op.descricao, op.projeto_cod, op.tarefa_cod,
                op.nome_fornecedor, op.status_operacional,
                formata_dt(op.emissao_sc),
                op.qtd_solicitada, op.qtd_pedida, op.qtd_recebida, op.residuo
            ])

        return response

    # KPIs
    kpis = {
        'pendentes_cotacao': operacoes.filter(status_operacional='PENDENTE COTAÇÃO').count(),
        'compras_parciais': operacoes.filter(status_operacional='COMPRA PARCIAL').count(),
        'entregas_parciais': operacoes.filter(status_operacional='ENTREGA PARCIAL').count(),
        'aguardando_entrega': operacoes.filter(status_operacional='AGUARDANDO ENTREGA').count(),
    }

    # Listas do Filtro
    lista_projetos = OperacaoCompras.objects.exclude(projeto_cod='').values_list('projeto_cod', flat=True).distinct().order_by('projeto_cod')
    lista_status = OperacaoCompras.objects.exclude(status_operacional='').values_list('status_operacional', flat=True).distinct().order_by('status_operacional')

    paginator = Paginator(operacoes, 50)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_filtros = query_params.urlencode()

    # Contexto
    context = {
        'operacoes': page_obj,
        'kpis': kpis,
        'lista_projetos': lista_projetos,
        'lista_status': lista_status,
        'url_filtros': url_filtros,
        'filtros': {
            'projeto': projeto_filtro,
            'status': status_filtro,
            'pedido': pedido_filtro,
            'nota': nota_filtro,
            'num_sc': sc_filtro,
            'nome_fornecedor': fornecedor_filtro,
        }
    }

    return render(request, 'compras/dashboard_operacional.html', context)
