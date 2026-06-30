import json
import logging
import statistics
from django.core.cache import cache
from django.db.models import Count
from django.http import JsonResponse

from compras.selectors import PmsDashboardSelector
from compras.services.business import ComprasBusinessService
from compras.services.csv_exporters import gerar_csv_operacoes_compras, gerar_csv_ranking_fornecedores
from django.views.decorators.http import require_POST
from .tasks import (
    LOCK_SYNC_COMPRAS,
    LOCK_SYNC_COMPRAS_PMS,
    task_sincronizar_pms_protheus,
    task_sincronizar_protheus,
)
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.decorators import group_required
from .models import OperacaoCompras, AvaliacaoFornecedor, PerguntaAvaliacao, RespostaAvaliacao

logger = logging.getLogger(__name__)

@login_required(login_url='/login/')
@group_required(['Compras'])
def dashboard_compras(request):
    context = PmsDashboardSelector.get_context(filtros={
        'projeto': request.GET.get('projeto'),
        'page': request.GET.get('page'),
    })
    return render(request, 'compras/dashboard.html', context)

@login_required(login_url='/login/')
@group_required(['Compras'])
@require_POST
def atualizar_dados_pms(request):
    if not request.user.is_staff:
        return JsonResponse({
            "status": "forbidden",
            "message": "A sincronizacao manual PMS exige acesso administrativo."
        }, status=403)

    if not cache.add(LOCK_SYNC_COMPRAS_PMS, True, timeout=3600):
        return JsonResponse({
            "status": "locked",
            "message": "Sincronização PMS já em andamento."
        })

    try:
        task = task_sincronizar_pms_protheus.delay()
    except Exception:
        cache.delete(LOCK_SYNC_COMPRAS_PMS)
        logger.exception("Falha ao publicar sincronizacao PMS de Compras no Celery.")
        return JsonResponse({
            "status": "error",
            "message": "Nao foi possivel iniciar a sincronizacao PMS."
        }, status=503)

    return JsonResponse({
        "status": "processing",
        "task_id": task.id,
        "message": "Sincronização PMS iniciada em segundo plano."
    })


# ⬆️ Atualizado com o novo fluxo
# ⬇️ Legado com o antigo fluxo


@login_required(login_url='/login/')
@group_required(['Compras'])
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
@group_required(['Compras'])
def dashboard_avaliacoes(request):
    """
    Dashboard de Análise de Desempenho.
    View limpa, focada apenas em orquestração e contexto.
    """
    # Delega a lógica de negócio pesada para o Service Layer
    ranking_data = ComprasBusinessService.processar_ranking_fornecedores()

    # Preparação para o Chart.js (apenas formatação visual)
    labels = [r['fornecedor'][:20] + "..." if len(r['fornecedor']) > 20 else r['fornecedor'] for r in ranking_data]
    medians = [r['mediana'] for r in ranking_data]

    # Lógica de cores mantida, mas agora o 'risco' já vem calculado do serviço
    cores = ['#dc3545' if r['risco'] else '#0d6efd' for r in ranking_data]

    context = {
        'ranking': ranking_data,
        'total_avaliacoes': sum(r['qtd_avaliacoes'] for r in ranking_data),
        'fornecedores_avaliados': len(ranking_data),
        'fornecedores_risco': sum(1 for r in ranking_data if r['risco']),
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(medians),
        'chart_colors': json.dumps(cores),
    }

    return render(request, 'compras/avaliacoes/dashboard_avaliacoes.html', context)


@login_required(login_url='/login/')
@group_required(['Compras'])
@require_POST
def atualizar_dados_dw(request):
    if not request.user.is_staff:
        return JsonResponse({
            "status": "forbidden",
            "message": "A sincronizacao manual legada exige acesso administrativo."
        }, status=403)

    if not cache.add(LOCK_SYNC_COMPRAS, True, timeout=3600):
        return JsonResponse({
            "status": "locked",
            "message": "Sincronização já em andamento."
        })

    # Dispara a task assíncrona
    try:
        task = task_sincronizar_protheus.delay()
    except Exception:
        cache.delete(LOCK_SYNC_COMPRAS)
        logger.exception("Falha ao publicar sincronizacao legada de Compras no Celery.")
        return JsonResponse({
            "status": "error",
            "message": "Nao foi possivel iniciar a sincronizacao legada."
        }, status=503)

    return JsonResponse({
        "status": "processing",
        "task_id": task.id,
        "message": "Sincronização iniciada em segundo plano."
    })


@login_required(login_url='/login/')
@group_required(['Compras'])
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
@group_required(['Compras'])
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
@group_required(['Compras'])
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

