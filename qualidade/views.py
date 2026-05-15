import json
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .models import RNC, Local, Equipamento, RNCImagem, RNCEficaciaImagem, RNCEficaciaPDF
from .service import RNCService
from core.decorators import exige_permissao

from rest_framework.decorators import api_view
from rest_framework.response import Response
from . serializers import RNCSerializer

User = get_user_model()

@login_required(login_url='/login/')
def dashboard_qualidade(request):
    usuario_sgq = request.user.pode_acessar_modulo('qualidade')

    locais_ativos = Local.objects.filter(ativo= True)
    equipamento_ativos = Equipamento.objects.filter(ativo= True)

    usuarios_ativos = User.objects.filter(is_active=True).order_by('first_name')

    context = {
        'locais': locais_ativos,
        'equipamentos': equipamento_ativos,
        'usuarios': usuarios_ativos,
        'is_sgq': usuario_sgq
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
        'responsaveis', 'imagens', 'eficacia_imagens', 'eficacia_pdfs'
    ).all().order_by('-id')

    data = []
    for rnc in rncs:
        nomes_responsaveis = ", ".join([resp.get_full_name() or resp.username for resp in rnc.responsaveis.all()])
        imagens_dados = [{'id': img.id, 'url': img.imagem.url} for img in rnc.imagens.all() if img.imagem]
        eficacia_imagens_dados = [{'id': img.id, 'url': img.imagens_eficacia.url} for img in rnc.eficacia_imagens.all()if img.imagens_eficacia]
        pdfs_dados = [{'id': pdf.id, 'url': pdf.arquivo_pdf.url} for pdf in rnc.eficacia_pdfs.all() if pdf.arquivo_pdf]

        data.append({
            'id': rnc.id,
            'registrador': rnc.registrador.get_full_name() or rnc.registrador.username,
            'registrador_id': rnc.registrador.id if rnc.registrador else None,
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
            'pdfs_dados': pdfs_dados,
            'qtd_imagens': len(imagens_dados),
            'primeira_imagem_url': imagens_dados[0] if imagens_dados else '',
            'imagens_dados': imagens_dados,
            'eficacia_imagens_dados': eficacia_imagens_dados,
            'qtd_imagens_eficacia': len(eficacia_imagens_dados),
            'primeira_imagem_eficacia_url': eficacia_imagens_dados[0] if eficacia_imagens_dados else '',
            'status_code': rnc.status,
            'categoria_code': rnc.categoria,
            'origem_code': rnc.origem,
            'criticidade_code': rnc.criticidade,
            'detector_code': rnc.detector,
            'equipamento_id': rnc.equipamento.id if rnc.equipamento else '',
            'local_id': rnc.local.id if rnc.local else '',
        })

    return JsonResponse(data, safe=False)


@login_required(login_url='/login/')
@require_POST
def api_atualizar_rnc(request, rnc_id):

    try:
        dados = json.loads(request.body)
        campo = dados.get('campo')
        valor = dados.get('valor')

        is_sgq = request.user.pode_acessar_modulo('qualidade')

        campos_sgq = [
            'projeto_cod', 'elemento_rastreador', 'detector', 'categoria',
            'origem', 'criticidade', 'status', 'equipamento', 'local',
            'descricao', 'correcao', 'ishikawa_link', 'causas_principais',
            'acao_corretiva', 'eficacia_texto', 'data_encerramento',
            'data_prevista_conclusao', 'registrador'
        ]

        campos_gerais = ['correcao', 'causas_principais', 'acao_corretiva', 'ishikawa_link', 'descricao', 'eficacia_texto']

        permitidos = campos_sgq if is_sgq else campos_gerais

        if campo not in permitidos:
            return JsonResponse({'status': 'erro', 'mensagem': 'Edição deste campo não autorizada para o seu perfil.'}, status=403)

        RNCService.atualizar_rnc(rnc_id, campo, valor)
        return JsonResponse({'status': 'sucesso'})

    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=500)


@login_required(login_url='/login/')
@api_view(['POST'])
def api_criar_rnc(request):
    dados = request.data.copy()
    dados['status'] = 'PR'
    dados['local'] = dados.get('local_id')
    if dados.get('equipamento_id'):
        dados['equipamento'] = dados.get('equipamento_id')
    dados['registrador'] = dados.get('registrador_id') or request.user.id
    dados['status'] = 'PR'
    serializer = RNCSerializer(data=dados)

    if serializer.is_valid():
        # O .save() aqui executa automaticamente o RNC.objects.create() por baixo dos panos!
        nova_rnc = serializer.save()
        responsaveis_ids = dados.get('responsaveis', [])
        if responsaveis_ids:
            nova_rnc.responsaveis.set(responsaveis_ids)
            RNCService.notificar_nova_rnc(nova_rnc.id, responsaveis_ids)
        return Response({'status': 'sucesso', 'rnc_id': nova_rnc.id})
    else:
        print(f"ERROS DE VALIDAÇÃO: {serializer.errors}")
        return Response({'status': 'erro', 'mensagem': serializer.errors}, status=400)


@login_required(login_url='/login/')
@api_view(['POST'])
def api_editar_rnc_avancado(request, rnc_id):
    rnc = get_object_or_404(RNC, id=rnc_id)
    is_sgq = request.user.pode_acessar_modulo('qualidade')

    data_antiga = rnc.data_encerramento
    data_previsao = rnc.data_prevista_conclusao

    dados = request.data.copy()

    if not is_sgq:
        campos_proibidos = [
            'status', 'categoria', 'origem', 'criticidade', 'detector',
            'local', 'equipamento', 'data_encerramento', 'data_prevista_conclusao', 'descricao'
        ]
        for campo in campos_proibidos:
            dados.pop(campo, None)

    serializer = RNCSerializer(instance=rnc, data=dados, partial=True)

    if serializer.is_valid():
        rnc_atualizada = serializer.save()

        imagens = request.FILES.getlist('imagens')
        for img in imagens:
            RNCImagem.objects.create(rnc=rnc_atualizada, imagem=img)

        imagens_eficacia = request.FILES.getlist('imagens_eficacia')
        for img in imagens_eficacia:
            RNCEficaciaImagem.objects.create(rnc=rnc_atualizada, imagens_eficacia=img)

        pdfs_eficacia = request.FILES.getlist('eficacia_pdfs_multiplos')
        for pdf in pdfs_eficacia:
            RNCEficaciaPDF.objects.create(rnc=rnc_atualizada, arquivo_pdf=pdf)


        if rnc_atualizada.data_encerramento and rnc_atualizada.data_encerramento != data_antiga:
            RNCService._notificar_data_encerramento(rnc_atualizada.id)

        if rnc_atualizada.data_prevista_conclusao and rnc_atualizada.data_prevista_conclusao != data_previsao:
            RNCService._notificar_data_previsao(rnc_atualizada.id)

        return Response({'status': 'sucesso'})
    else:
        return Response({'status': 'erro', 'mensagem': serializer.errors}, status=400)


@login_required(login_url='/login/')
@require_POST
def api_deletar_midia_rnc(request, tipo, midia_id):
    try:
        if tipo == 'padrao':
            midia = get_object_or_404(RNCImagem, id=midia_id)
            if midia.imagem:
                midia.imagem.delete(save=False)
            midia.delete()

        elif tipo == 'eficacia':
            midia_eficacia = get_object_or_404(RNCEficaciaImagem, id=midia_id)
            if midia_eficacia.imagens_eficacia:
                midia_eficacia.imagens_eficacia.delete(save=False)
            midia_eficacia.delete()


        elif tipo == 'pdf':
            rncpdf = get_object_or_404(RNCEficaciaPDF, id=midia_id)
            if rncpdf.arquivo_pdf:
                rncpdf.arquivo_pdf.delete(save=False)
            rncpdf.delete()
        else:
            return JsonResponse({'status': 'erro', 'mensagem': 'Tipo de mídia inválido não reconhecido pela API.'}, status=400)
        return JsonResponse({'status': 'sucesso'})

    except Exception as e:
        return JsonResponse({'status': 'erro', 'mensagem': str(e)}, status=500)