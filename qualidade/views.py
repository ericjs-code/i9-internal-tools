import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist

# Importações dos seus modelos e do nosso novo Service
from .models import RNC
from .service import RNCService

@login_required(login_url='/login/')
def dashboard_qualidade(request):
    return render(request, 'qualidade/dashboard.html')


@login_required(login_url='/login/')
def api_listar_rncs(request):
    """
    Retorna a lista completa de RNCs em formato JSON, incluindo textos e mídias.
    """
    rncs = RNC.objects.select_related(
        'registrador', 'equipamento', 'local', 'tipo_nc'
    ).prefetch_related(
        'responsaveis', 'imagens'
    ).all().order_by('-id')

    data = []
    for rnc in rncs:
        nomes_responsaveis = ", ".join([resp.get_full_name() or resp.username for resp in rnc.responsaveis.all()])
        imagens_urls = [img.imagem.url for img in rnc.imagens.all() if img.imagem]

        data.append({
            'id': rnc.id,
            'registrador': rnc.registrador.get_full_name() or rnc.registrador.username,
            'data_abertura': rnc.data_abertura.strftime('%Y/%m/%d') if rnc.data_abertura else '',
            'projeto_cod': rnc.projeto_cod or '-',
            'elemento_rastreador': rnc.elemento_rastreador or '-',
            'detector': rnc.get_detector_display(),
            'classificacao': rnc.get_classificacao_display(),
            'criticidade': rnc.get_criticidade_display(),
            'status': rnc.get_status_display(),
            'equipamento': rnc.equipamento.nome if rnc.equipamento else 'N/A',
            'local': rnc.local.nome if rnc.local else '-',
            'tipo_nc': rnc.tipo_nc.nome if rnc.tipo_nc else '-',
            'responsaveis': nomes_responsaveis,
            'data_prevista_conclusao': rnc.data_prevista_conclusao.strftime('%Y/%m/%d') if rnc.data_prevista_conclusao else '',
            'data_encerramento': rnc.data_encerramento.strftime('%Y/%m/%d') if rnc.data_encerramento else '',
            'justificativa_criticidade': rnc.justificativa_criticidade or '',
            'descricao': rnc.descricao or '',
            'correcao': rnc.correcao or '',
            'ishikawa_link': rnc.ishikawa_link or '',
            'causas_principais': rnc.causas_principais or '',
            'acao_corretiva': rnc.acao_corretiva or '',
            'eficacia_texto': rnc.eficacia_texto or '',
            'eficacia_pdf': rnc.eficacia_pdf.url if rnc.eficacia_pdf else '',
            'qtd_imagens': len(imagens_urls),
            'primeira_imagem_url': imagens_urls[0] if imagens_urls else '',
        })

    return JsonResponse(data, safe=False)


@login_required(login_url='/login/')
@require_POST
def api_atualizar_rnc(request, rnc_id):
    try:
        dados = json.loads(request.body)
        campo = dados.get('campo')
        valor = dados.get('valor')

        campos_permitidos = [
            'projeto_cod',
            'elemento_rastreador',
            'detector',
            'classificacao',
            'criticidade',
            'justificativa_criticidade',
            'status',
            'equipamento',
            'local',
            'tipo_nc',
            'descricao',
            'correcao',
            'ishikawa_link',
            'causas_principais',
            'acao_corretiva',
            'eficacia_texto',
            'eficacia_pdf',
            'responsaveis',
            'data_encerramento',
            'versao',
        ]

        # Se o utilizador tentar enviar um campo que não está na lista, bloqueamos com erro 403 (Forbidden)
        if campo not in campos_permitidos:
            return JsonResponse({'status': 'erro', 'mensagem': 'Edição deste campo não autorizada.'}, status=403)

        # Se passou na segurança, delegamos a inteligência para o Service
        RNCService.atualizar_rnc(rnc_id, campo, valor)
        return JsonResponse({'status': 'sucesso'})

    except RNC.DoesNotExist:
        return JsonResponse({'status': 'erro', 'mensagem': 'RNC não encontrada.'}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'erro', 'mensagem': 'Dados inválidos.'}, status=400)

    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=500)