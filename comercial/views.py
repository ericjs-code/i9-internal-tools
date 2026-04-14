import csv
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from datetime import date
from .forms import STOForm, VersaoFormularioSTOForm
from .models import STO, STOImagem, STORevisao, VersaoFormularioSTO
from core.decorators import exige_permissao


@login_required(login_url='/login/')
@exige_permissao(['comercial'])
def criar_sto(request):
    if request.method == 'POST':
        form = STOForm(request.POST, request.FILES)
        if form.is_valid():
            sto = form.save(commit=False)
            sto.consultor = request.user

            sto.versao_formulario = VersaoFormularioSTO.obter_versao_ativa_ou_padrao()

            sto.save()

            arquivos = request.FILES.getlist('imagens')
            for f in arquivos:
                STOImagem.objects.create(sto=sto, imagem=f)

            messages.success(request, 'Solicitação Técnica de Orçamento (STO) salva com sucesso!')
            return redirect('listar_stos')
    else:
        form = STOForm()

    return render(request, 'comercial/sto_form.html', {'form': form})


@login_required(login_url='/login/')
@exige_permissao(['comercial'])
def listar_stos(request):
    stos = STO.objects.all().order_by('-data', '-id')
    return render(request, 'comercial/sto_lista.html', {'stos': stos})


@login_required(login_url='login/')
@exige_permissao(['comercial'])
def exportar_stos_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="relatorio_stos_i9tmg.csv"'
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'ID', 'Código STO', 'Data', 'Consultor', 'Cliente', 'Contato', 'Cidade',
        'Atividade', 'Capacidade (T/h)', 'Produto'
    ])

    stos = STO.objects.all().order_by('-id')
    for sto in stos:
        writer.writerow([
            sto.id,
            sto.codigo,
            sto.data.strftime('%d/%m/%Y'),
            sto.consultor.get_full_name() or sto.consultor.username,
            sto.cliente,
            sto.contato,
            sto.cidade,
            sto.atividade,
            sto.capacidade_fabrica,
            sto.produto
        ])

    return response


@login_required(login_url='/login/')
@exige_permissao(['comercial'])
def ver_sto(request, pk):
    sto = get_object_or_404(STO, pk=pk)
    return render(request, 'comercial/sto_detalhe.html', {'sto': sto})


@login_required(login_url='/login/')
@exige_permissao(['comercial'])
def editar_sto(request, pk):
    sto = get_object_or_404(STO, pk=pk)

    if request.method == 'POST':
        form = STOForm(request.POST, request.FILES, instance=sto)
        if form.is_valid():
            sto = form.save()


            solicitante_alt = form.cleaned_data.get('solicitante_alteracao')
            motivo_alt = form.cleaned_data.get('motivo_alteracao')

            if solicitante_alt and motivo_alt:
                STORevisao.objects.create(
                    sto=sto,
                    usuario_modificador=request.user,
                    solicitante=solicitante_alt,
                    motivo_alteracao=motivo_alt
                )

            arquivos = request.FILES.getlist('imagens')
            for f in arquivos:
                STOImagem.objects.create(sto=sto, imagem=f)

            messages.success(request, 'STO atualizada com sucesso! O log de revisão foi registrado.')
            return redirect('ver_sto', pk=sto.id)
    else:
        form = STOForm(instance=sto)

    return render(request, 'comercial/sto_form.html', {'form': form, 'sto': sto})


@login_required(login_url='/login/')
@exige_permissao(['comercial'])
def historico_versoes_iso(request):
    if request.method == 'POST':
        form = VersaoFormularioSTOForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Nova versão da ISO ativada com sucesso!')
            return redirect('historico_versoes_iso')
    else:
        form = VersaoFormularioSTOForm()

    versoes = VersaoFormularioSTO.objects.all().order_by('-data_inicio')

    context = {
        'versoes': versoes,
        'form': form
    }

    return render(request, 'comercial/iso_versoes.html', context)