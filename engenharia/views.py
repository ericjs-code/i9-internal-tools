import pandas as pd
from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.core.cache import cache
from .task import task_sincronizar_protheus


from core.decorators import exige_permissao
from .models import EstruturaProduto


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def extrai_estrutura_simples(request):
    # Busca padrão
    estruturas = EstruturaProduto.objects.all().order_by('codigo_pai', 'nivel')

    # Captura o que o usuário digitou no Input de busca do HTML
    busca = request.GET.get('busca')

    # Se ele digitou algo, aplica o filtro no banco!
    if busca:
        estruturas = estruturas.filter(
            Q(codigo_pai__icontains=busca) |
            Q(codigo_componente__icontains=busca) |
            Q(descricao_pai__icontains=busca) |
            Q(descricao_componente__icontains=busca)
        )

    context = {
        'estruturas': estruturas
    }
    return render(request, 'engenharia/extrai_estrutura_simples.html', context)



@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def exportar_estrutura_excel(request):
    """Gera um arquivo Excel fresh a partir dos dados do banco"""
    # Busca os dados
    estruturas = EstruturaProduto.objects.all().values()
    df = pd.DataFrame(list(estruturas))

    cols_datetime_com_tz = df.select_dtypes(include=['datetimetz']).columns

    for col in cols_datetime_com_tz:
        df[col] = df[col].dt.tz_localize(None)

    # 2. Configura a Resposta HTTP para Excel
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Relatorio_Engenharia.xlsx"'

    # 3. Salva o DataFrame direto na resposta
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

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