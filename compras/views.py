import json
import statistics
from dotenv import load_dotenv
from django.core.cache import cache
from celery.result import AsyncResult
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from .models import DataWarehouseCompras
from django.views.decorators.http import require_POST
from .services import gerar_csv_operacoes_compras, gerar_csv_gerencial_compras, gerar_csv_ranking_fornecedores
from .task import task_sincronizar_protheus
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.decorators import exige_permissao
from .models import OperacaoCompras, AvaliacaoFornecedor, PerguntaAvaliacao, RespostaAvaliacao

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


@login_required(login_url='/login/')
@exige_permissao(['compras'])
def listar_pedidos_avaliacao(request):
    """
    Listagem de pedidos disponíveis para avaliação de fornecedores.
    """
    avaliacao_subquery = AvaliacaoFornecedor.objects.filter(
        num_pedido=OuterRef('num_pedidos_vinculados')
    )

    base_query = OperacaoCompras.objects.exclude(num_pedidos_vinculados='').filter(
        status_operacional__in=['ENTREGA PARCIAL', 'ATENDIDO TOTAL']
    )

    # Query Base
    pedidos = base_query.values(
        'num_pedidos_vinculados',
        'nome_fornecedor',
        'projeto_cod',
        'tipo_produto',
        'emissao_ultimo_pedido'
    ).annotate(
        total_itens=Count('id'),
        is_avaliado=Exists(avaliacao_subquery) 
    ).order_by('-emissao_ultimo_pedido')


    # Captura dos Parâmetros GET
    fornecedor = request.GET.get('nome_fornecedor')
    numero_pedido = request.GET.get('num_pedido')
    tipo_produto = request.GET.get('tipo_produto')

    # Aplicação dosFiltros na Query Base
    if fornecedor:
        pedidos = pedidos.filter(nome_fornecedor__icontains=fornecedor)
    if numero_pedido:
        pedidos = pedidos.filter(num_pedidos_vinculados__icontains=numero_pedido)
    if tipo_produto:
        pedidos = pedidos.filter(tipo_produto=tipo_produto)


    # Listas para popular os <select> do HTML
    lista_fornecedores = OperacaoCompras.objects.exclude(nome_fornecedor='').values_list('nome_fornecedor', flat=True).distinct().order_by(
        'nome_fornecedor')
    lista_tipos = OperacaoCompras.objects.exclude(tipo_produto='').values_list('tipo_produto', flat=True).distinct().order_by(
        'tipo_produto')

    # Paginação Padrão
    paginator = Paginator(pedidos, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Preservando a URL para a paginação
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_filtros = query_params.urlencode()

    context = {
        'pedidos': page_obj,
        'lista_fornecedores': lista_fornecedores,
        'lista_tipos': lista_tipos,
        'url_filtros': url_filtros,
        'filtros': {
            'nome_fornecedor': fornecedor,
            'num_pedido': numero_pedido,
            'tipo_produto': tipo_produto,
        }
    }

    return render(request, 'compras/avaliacoes/listar_pedidos.html', context)



@login_required(login_url='/login/')
@exige_permissao(['compras'])
def nova_avaliacao_fornecedor(request, numero_pedido):
    """
    Formulário de avaliação e processamento do POST com transação segura.
    Granularidade: Pedido + Tipo de Produto.
    """
    tipo_produto = request.GET.get('tipo', '')

    # Busca os dados brutos da Operação Base para pré-preencher a tela
    operacao_base = OperacaoCompras.objects.filter(
        num_pedidos_vinculados=numero_pedido,
        tipo_produto=tipo_produto
    ).first()

    if not operacao_base:
        messages.error(request, "Pedido ou Tipo de Produto não encontrado na base operacional.")
        return redirect('listar_pedidos_avaliacao')

    # Checa se esse bloco exato (Pedido + Tipo) já foi avaliado
    ja_avaliado = AvaliacaoFornecedor.objects.filter(
        num_pedido=numero_pedido,
        tipo_produto=tipo_produto
    ).exists()

    if ja_avaliado:
        messages.warning(request, f"O pedido {numero_pedido} para o setor '{tipo_produto}' já foi avaliado.")
        return redirect('listar_pedidos_avaliacao')

    perguntas = PerguntaAvaliacao.objects.filter(ativa=True).order_by('ordem')

    # PROCESSAMENTO DO FORMULÁRIO (POST)
    if request.method == 'POST':
        try:
            with transaction.atomic():

                # Cria o Cabeçalho da Avaliação
                nova_avaliacao = AvaliacaoFornecedor.objects.create(
                    num_pedido=numero_pedido,
                    cod_fornecedor=operacao_base.num_fornecedor if hasattr(operacao_base,'num_fornecedor') else getattr(operacao_base, 'cod_fornecedor', ''),
                    nome_fornecedor=operacao_base.nome_fornecedor,
                    cnpj=operacao_base.cnpj,
                    projeto=operacao_base.projeto_cod,
                    tipo_produto=tipo_produto,
                    avaliador=request.user
                )

                # Varre as perguntas ativas para salvar as respostas
                for pergunta in perguntas:
                    # O HTML enviará inputs com name="nota_1", "justificativa_1", etc.
                    str_nota = request.POST.get(f'nota_{pergunta.id}')
                    justificativa = request.POST.get(f'justificativa_{pergunta.id}', '').strip()

                    # Validação de segurança
                    if str_nota is None or str_nota == '':
                        raise ValueError(f"A pergunta '{pergunta.texto}' não foi respondida.")

                    nota_int = int(str_nota)

                    # Regra de Negócio Crítica: Nota 0 exige justificativa
                    if nota_int == 0 and not justificativa:
                        raise ValueError(
                            f"A nota 0 na pergunta '{pergunta.texto}' exige uma justificativa obrigatória.")

                    # Salva a resposta vinculada à avaliação e à pergunta
                    RespostaAvaliacao.objects.create(
                        avaliacao=nova_avaliacao,
                        pergunta=pergunta,
                        nota=nota_int,
                        justificativa=justificativa if nota_int == 0 else ''  # Força justificativa vazia se nota 10
                    )

            messages.success(request, "Avaliação registrada com sucesso!")
            return redirect('listar_pedidos_avaliacao')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Erro interno ao salvar avaliação: {str(e)}")

    context = {
        'operacao': operacao_base,
        'perguntas': perguntas,
    }

    return render(request, 'compras/avaliacoes/form_avaliacao.html', context)



@login_required(login_url='/login/')
@exige_permissao(['compras'])
def dashboard_avaliacoes(request):
    """
    Dashboard de Análise de Desempenho dos Fornecedores.
    Calcula a mediana das notas e identifica fornecedores abaixo do corte de 8.0.
    """
    # Busca todas as avaliações e faz um "join" com as respostas para otimizar o banco
    avaliacoes = AvaliacaoFornecedor.objects.prefetch_related('respostas').all()

    fornecedores_data = {}

    # Agrupamento de dados por Fornecedor
    for aval in avaliacoes:
        fornecedor = aval.nome_fornecedor
        if fornecedor not in fornecedores_data:
            fornecedores_data[fornecedor] = {'notas_avaliacoes': [], 'qtd_avaliacoes': 0}

        fornecedores_data[fornecedor]['qtd_avaliacoes'] += 1

        notas_aval = [resp.nota for resp in aval.respostas.all()]
        if notas_aval:
            media_do_pedido = sum(notas_aval) / len(notas_aval)
            fornecedores_data[fornecedor]['notas_avaliacoes'].append(media_do_pedido)

    ranking = []
    fornecedores_risco = 0
    nota_corte = 8.0

    # Processamento Estatístico (Mediana das Médias)
    for f_nome, data in fornecedores_data.items():
        mediana_final = statistics.median(data['notas_avaliacoes']) if data['notas_avaliacoes'] else 0
        abaixo_corte = mediana_final < nota_corte

        if abaixo_corte:
            fornecedores_risco += 1

        ranking.append({
            'fornecedor': f_nome,
            'mediana': mediana_final,
            'qtd_avaliacoes': data['qtd_avaliacoes'],
            'risco': abaixo_corte
        })

    # Ordenar ranking: Menores notas primeiro (para destacar os piores)
    ranking.sort(key=lambda x: (x['mediana'], -x['qtd_avaliacoes']))

    # Preparação dos dados para o Gráfico (Chart.js)
    labels = [r['fornecedor'][:20] + "..." if len(r['fornecedor']) > 20 else r['fornecedor'] for r in ranking]
    medians = [r['mediana'] for r in ranking]

    # Cores: Vermelho para < 8.0, Azul para >= 8.0
    cores = ['#dc3545' if r['risco'] else '#0d6efd' for r in ranking]

    context = {
        'ranking': ranking,
        'total_avaliacoes': avaliacoes.count(),
        'fornecedores_avaliados': len(ranking),
        'fornecedores_risco': fornecedores_risco,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(medians),
        'chart_colors': json.dumps(cores),
        'nota_corte': nota_corte
    }

    return render(request, 'compras/avaliacoes/dashboard_avaliacoes.html', context)


@login_required(login_url='/login/')
@exige_permissao(['compras'])
def exportar_ranking_csv(request):
    """
    Prepara os dados do ranking e delega a geração do arquivo para o services.py
    """
    avaliacoes = AvaliacaoFornecedor.objects.prefetch_related('respostas').all()
    fornecedores_data = {}

    for aval in avaliacoes:
        fornecedor = aval.nome_fornecedor
        if fornecedor not in fornecedores_data:
            fornecedores_data[fornecedor] = {'notas_avaliacoes': [], 'qtd_avaliacoes': 0}

        fornecedores_data[fornecedor]['qtd_avaliacoes'] += 1

        notas_aval = [resp.nota for resp in aval.respostas.all()]
        if notas_aval:
            media_do_pedido = sum(notas_aval) / len(notas_aval)
            fornecedores_data[fornecedor]['notas_avaliacoes'].append(media_do_pedido)

    ranking = []
    for f_nome, data in fornecedores_data.items():
        mediana_final = statistics.median(data['notas_avaliacoes']) if data['notas_avaliacoes'] else 0
        ranking.append({
            'fornecedor': f_nome,
            'mediana': mediana_final,
            'qtd_avaliacoes': data['qtd_avaliacoes']
        })

    ranking.sort(key=lambda x: (x['mediana'], -x['qtd_avaliacoes']))

    # View delegando o trabalho sujo para a camada de serviço:
    return gerar_csv_ranking_fornecedores(ranking)