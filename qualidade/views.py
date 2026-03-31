import json
from datetime import datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .models import RNC, Local, Equipamento, RNCImagem, RNCEficaciaImagem
from .service import RNCService

User = get_user_model()

@login_required(login_url='/login/')
def dashboard_qualidade(request):
    locais_ativos = Local.objects.filter(ativo= True)
    equipamento_ativos = Equipamento.objects.filter(ativo= True),

    usuarios_ativos = User.objects.filter(is_active=True).order_by('first_name')

    context = {
        'locais': locais_ativos,
        'equipamentos': equipamento_ativos,
        'usuarios': usuarios_ativos
    }
    return render(request, 'qualidade/dashboard.html', context)


@login_required(login_url='/login/')
def api_listar_rncs(request):
    """
    Retorna a lista completa de RNCs em formato JSON, incluindo textos e mídias.
    """
    rncs = RNC.objects.select_related(
        'registrador', 'equipamento', 'local'
    ).prefetch_related(
        'responsaveis', 'imagens', 'eficacia_imagens'
    ).all().order_by('-id')

    data = []
    for rnc in rncs:
        nomes_responsaveis = ", ".join([resp.get_full_name() or resp.username for resp in rnc.responsaveis.all()])
        imagens_urls = [img.imagem.url for img in rnc.imagens.all() if img.imagem]
        imagens_eficacia_urls = [img.imagens_eficacia.url for img in rnc.eficacia_imagens.all() if img.imagens_eficacia]

        data.append({
            'id': rnc.id,
            'registrador': rnc.registrador.get_full_name() or rnc.registrador.username,
            'data_abertura': rnc.data_abertura.strftime('%Y/%m/%d') if rnc.data_abertura else '',
            'projeto_cod': rnc.projeto_cod or '-',
            'elemento_rastreador': rnc.elemento_rastreador or '-',
            'detector': rnc.get_detector_display(),
            'categoria': rnc.get_categoria_display(),
            'origem': rnc.get_origem_display(),
            'criticidade': rnc.get_criticidade_display(),
            'status': rnc.get_status_display(),
            'equipamento': rnc.equipamento.nome if rnc.equipamento else 'N/A',
            'local': rnc.local.nome if rnc.local else '-',
            'responsaveis': nomes_responsaveis,
            'responsaveis_ids': [resp.id for resp in rnc.responsaveis.all()],
            'data_prevista_conclusao': rnc.data_prevista_conclusao.strftime('%Y/%m/%d') if rnc.data_prevista_conclusao else '',
            'data_encerramento': rnc.data_encerramento.strftime('%Y/%m/%d') if rnc.data_encerramento else '',
            'descricao': rnc.descricao or '',
            'correcao': rnc.correcao or '',
            'ishikawa_link': rnc.ishikawa_link or '',
            'causas_principais': rnc.causas_principais or '',
            'acao_corretiva': rnc.acao_corretiva or '',
            'eficacia_texto': rnc.eficacia_texto or '',
            'eficacia_pdf': rnc.eficacia_pdf.url if rnc.eficacia_pdf else '',
            'qtd_imagens': len(imagens_urls),
            'primeira_imagem_url': imagens_urls[0] if imagens_urls else '',
            'imagens_urls': imagens_urls,
            'eficacia_imagens_urls': imagens_eficacia_urls,
            'qtd_imagens_eficacia': len(imagens_eficacia_urls),
            'primeira_imagem_eficacia_url': imagens_eficacia_urls[0] if imagens_eficacia_urls else ''
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
            'categoria',
            'origem',
            'criticidade',
            'status',
            'equipamento',
            'local',
            'descricao',
            'correcao',
            'ishikawa_link',
            'causas_principais',
            'acao_corretiva',
            'eficacia_texto',
            'eficacia_pdf',
            'responsaveis',
            'data_encerramento',
            'data_previsao_conclusao',
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


@login_required(login_url='/login/')
@require_POST
def api_criar_rnc(request):
    try:
        dados = json.loads(request.body)

        local = Local.objects.get(id=dados.get('local_id'))

        equipamento_id = dados.get('equipamento_id')
        equipamento = Equipamento.objects.get(id=equipamento_id) if equipamento_id else None

        mapa_categoria = {'Comercial': 'CO', 'Engenharia': 'EN', 'PCP': 'PC', 'Fabricação': 'FA', 'Montagem': 'MO', 'Suprimentos': 'SU', 'Fornecedor': 'FO', 'Expedição': 'EX', 'Qualidade': 'QU', 'Recursos Humanos': 'RH', 'Financeiro': 'FI', 'SGQ': 'SG'}
        mapa_criticidade = {'Alto': 'A', 'Médio': 'M', 'Baixo': 'B'}
        mapa_detector = {'Cliente': 'CL', 'Interno': 'IN', 'Auditor Interno': 'AI', 'Auditor Externo': 'AE', 'Fornecedor': 'FO'}
        mapa_origem = {'Comercial': 'CO', 'Projeto_Engenharia': 'PE', 'Fabricação': 'FA', 'Montagem_comissionamento': 'MC', 'Suprimentos': 'SU', 'RH': 'RH', 'Fornecedor': 'FO', 'Processo_interno_SGQ': 'SG'}

        nova_rnc = RNC.objects.create(
            registrador=request.user,
            local=local,
            equipamento=equipamento,
            detector=mapa_detector.get(dados.get('detector')),
            categoria=mapa_categoria.get(dados.get('categoria')),
            origem=mapa_origem.get(dados.get('origem')),
            criticidade=mapa_criticidade.get(dados.get('criticidade')),
            descricao=dados.get('descricao'),
            status = 'PR'
        )

        return JsonResponse({'status': 'sucesso', 'rnc_id': nova_rnc.id})

    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=400)


@login_required(login_url='/login/')
@require_POST
def api_editar_rnc_avancado(request, rnc_id):
    try:
        rnc = RNC.objects.get(id=rnc_id)

        data_antiga = rnc.data_encerramento

        data_encerramento = request.POST.get('data_encerramento')
        if data_encerramento:
            rnc.data_encerramento = datetime.strptime(data_encerramento, '%Y-%m-%d').date()
        elif data_encerramento == "":
            rnc.data_encerramento = None

        data_prevista = request.POST.get('data_prevista')
        if data_prevista:
            rnc.data_prevista_conclusao = datetime.strptime(data_prevista, '%Y-%m-%d').date()
        elif data_prevista == "":
            rnc.data_prevista_conclusao = None

        # 3. Tratamento do Ishikawa
        ishikawa_link = request.POST.get('ishikawa_link')
        if ishikawa_link is not None:
            rnc.ishikawa_link = ishikawa_link

        # 4. Tratamento dos Responsáveis
        responsaveis_ids = request.POST.getlist('responsaveis')
        if responsaveis_ids:
            rnc.responsaveis.set(responsaveis_ids)
        else:
            rnc.responsaveis.clear()

        # 5. Tratamento do PDF
        if 'eficacia_pdf' in request.FILES:
            rnc.eficacia_pdf = request.FILES['eficacia_pdf']

        # Salva o registo principal
        rnc.save()

        # 6. Tratamento das Imagens Adicionais
        imagens = request.FILES.getlist('imagens')
        for img in imagens:
            RNCImagem.objects.create(rnc=rnc, imagem=img)

        imagens_eficacia = request.FILES.getlist('imagens_eficacia')
        for img in imagens_eficacia:
            RNCEficaciaImagem.objects.create(rnc=rnc, imagens_eficacia=img)

        # 7. Gatilho do E-mail (Só dispara se a data de encerramento mudou E não for vazia)
        if rnc.data_encerramento and rnc.data_encerramento != data_antiga:
            RNCService._notificar_data_encerramento(rnc.id)

        return JsonResponse({'status': 'sucesso'})

    except Exception as e:
        print(f"ERRO NA EDIÇÃO AVANÇADA: {e}")
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=400)
