import pandas as pd
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from .task import task_sincronizar_protheus
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from engenharia.services.producao_service import ProducaoQueryService
from core.decorators import exige_permissao



@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def extrai_estrutura_simples(request):
    """
    View Principal Refatorada:
    - Busca apenas a lista paginada de projetos (VOs).
    - Delega o carregamento dos filhos para as APIs/partials via HTMX.
    """
    busca = request.GET.get('busca', '')

    # 1. Busca apenas a lista de VOs (projetos)
    lista_projetos = ProducaoQueryService.get_projetos_vo(termo_busca=busca)

    # 2. Pagina o resultado de forma eficiente
    paginator = Paginator(lista_projetos, 10)  # 10 projetos por página
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'page_obj': page_obj,  # O objeto de paginação agora contém os projetos
        'busca': busca
    }

    return render(request, 'engenharia/extrai_estrutura_simples.html', context)


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def get_conjuntos_pai(request, codigo_vo: str):
    """
    API/Partial View: Retorna os 'pais' de um 'vo' específico.
    Renderiza um template parcial que será injetado pelo HTMX.
    """
    busca = request.GET.get('busca', '')

    # Busca os conjuntos (pais) para o VO específico
    conjuntos = ProducaoQueryService.get_conjuntos_pai(codigo_vo=codigo_vo, termo_busca=busca)

    context = {
        'codigo_vo': codigo_vo,
        'conjuntos': conjuntos
    }

    # Este template parcial conterá apenas as linhas <tr> dos pais
    return render(request, 'engenharia/partials/_conjuntos_pai.html', context)


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def get_componentes_filho(request, codigo_vo: str, codigo_pai: str):
    """
    API/Partial View: Retorna os 'filhos' de um 'pai' e 'vo' específicos.
    Renderiza um template parcial que será injetado pelo HTMX.
    """
    busca = request.GET.get('busca', '')

    # Busca os componentes (filhos) para o PAI/VO específico
    componentes = ProducaoQueryService.get_componentes_filho(
        codigo_vo=codigo_vo,
        codigo_pai=codigo_pai,
        termo_busca=busca
    )

    context = {
        'componentes': componentes
    }

    # Este template parcial conterá apenas as linhas <tr> dos filhos
    return render(request, 'engenharia/partials/_componentes_filho.html', context)


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def exportar_estrutura_excel(request):
    """View Magra: Intermedia a requisição HTTP e o retorno do Excel."""

    # Capta o filtro de busca da URL, se o usuário estiver buscando algo específico
    busca = request.GET.get('busca', '')

    # Pede ao serviço o DataFrame pronto e limpo
    df = ProducaoQueryService.gerar_dataframe_exportacao(termo_busca=busca)

    # Configura a Resposta HTTP dizendo pro navegador que é um arquivo Excel
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Acompanhamento_Producao_Engenharia.xlsx"'

    # Grava o DataFrame diretamente na resposta de memória (Sem sujar o disco)
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        if df.empty:
            # Se vier vazio, exporta uma planilha com aviso
            pd.DataFrame([{"Aviso": "Nenhum dado encontrado para os filtros aplicados."}]).to_excel(writer, index=False)
        else:
            df.to_excel(writer, index=False, sheet_name='Analise_Producao')

    return response



@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
@require_POST
def atualizar_banco_estrutura(request):
    if cache.get('lock_sync_engenharia'):
        return JsonResponse({
            "status": "locked",
            "message": "Sincronização já em andamento."
        })

    cache.set('lock_sync_engenharia', True, timeout=600)

    # Dispara a task assíncrona
    task = task_sincronizar_protheus.delay()

    return JsonResponse({
        "status": "processing",
        "task_id": task.id,
        "message": "Sincronização iniciada em segundo plano."
    })