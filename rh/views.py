import csv
from django.db.models import Count, Case, When, Value, IntegerField
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from .models import Vaga, Candidatura, SolicitacaoVaga, PesquisaDemissional
from .forms import (CandidaturaForm, VagaForm, SolicitacaoVagaForm,
                    PesquisaDemissionalGeracaoForm, PesquisaDemissionalRespostaForm)
from core.decorators import exige_permissao

def portal_vagas(request):
    vagas = Vaga.objects.filter(ativa=True).order_by('-data_criacao')
    return render(request, 'rh/portal_vagas.html', {'vagas': vagas})


def aplicar_vaga(request, pk):
    vaga = get_object_or_404(Vaga, pk=pk, ativa=True)

    if request.method == 'POST':
        form = CandidaturaForm(request.POST, request.FILES)

        if form.is_valid():
            candidatura = form.save(commit=False)
            candidatura.vaga = vaga
            candidatura.save()

            messages.success(request, 'Currículo enviado com sucesso!')
            return redirect('portal_vagas')
    else:
        form = CandidaturaForm()

    return render(request, 'rh/aplicar_vaga.html', {'form': form, 'vaga': vaga})


@login_required(login_url='/admin/login')
@exige_permissao(['rh'])
def triagem_rh(request):
    """
    Prepara a lista de candidatos e os contadores para a tela inicial do RH
    Sempre que o usuario clica em um link ou acessa uma URL, o navegador empacoda dados(quem é o usuario, qual o IP, get ou post?
    e manda para o Django. O Django transforma isso no objeto 'request'
    """
    vaga_id = request.GET.get('vaga')

    vagas = Vaga.objects.all().order_by('-data_criacao')

    if vaga_id:
        candidaturas = Candidatura.objects.filter(vaga_id=vaga_id).order_by('-data_aplicacao')
        vaga_selecionada = get_object_or_404(Vaga, id=vaga_id)
    else:
        candidaturas = Candidatura.objects.all().order_by('-data_aplicacao')
        vaga_selecionada = None

    total_novos = Candidatura.objects.filter(status='NOVO').count()
    total_analise = Candidatura.objects.filter(status='EM_ANALISE').count()
    total_entrevistas = Candidatura.objects.filter(status='ENTREVISTA').count()

    context = {
        'vagas': vagas,
        'candidaturas': candidaturas,
        'vaga_selecionada': vaga_selecionada,
        'total_novos': total_novos,
        'total_analise': total_analise,
        'total_entrevistas': total_entrevistas
    }

    return  render(request, 'rh/triagem_rh.html', context)


@login_required(login_url='/admin/login')
@exige_permissao(['rh'])
def detalhe_candidato(request, pk):
    """
    Exibe o currículo de um candidato e permite o usuario mudar de fase (aprovar ou reprovar)
    o pk pe o id do candidato quem vem da url
    """
    candidatura =  get_object_or_404(Candidatura, pk=pk)

    if request.method == 'POST':
        novo_status = request.POST.get('status')
        obs = request.POST.get('observacoes_rh')

        if novo_status:
            candidatura.status = novo_status
        if obs is not None:
            candidatura.observacoes_rh = obs

        candidatura.save()

        messages.success(request, f'Avaliação de {candidatura.nome_completo} atualizada.')

        return redirect('detalhe_candidato', pk= candidatura.id)

    return render(request, 'rh/detalhe_candidato.html', {'candidatura': candidatura})


@login_required(login_url='/admin/login')
@exige_permissao(['rh', 'ti'])
def gestao_vagas(request):
    """
    Painel para o RH gerenciar as vagas abertas e fechadas. Usamos o annotate(count()) para o banco ja trazer a contagem
    de candidatos por vaga em uma unica query
    """
    vagas = Vaga.objects.annotate(total_candidatos=Count('candidaturas')).order_by('-ativa', '-data_criacao')

    vagas_abertas = vagas.filter(ativa=True).count()
    vagas_fechadas = vagas.filter(ativa=False).count()

    context = {
        'vagas': vagas,
        'vagas_abertas': vagas_abertas,
        'vagas_fechadas': vagas_fechadas
    }
    return render(request, 'rh/gestao_vagas.html', context)


@login_required(login_url='/login/')
def form_vaga(request, pk=None):
    if pk:
        vaga = get_object_or_404(Vaga, pk=pk)
        titulo_pagina = "Editar Vaga"
    else:
        vaga = None
        titulo_pagina = "Nova Vaga"

    if request.method == 'POST':
        form = VagaForm(request.POST, instance=vaga)
        if form.is_valid():
            nova_vaga = form.save(commit=False)

            if not pk:
                nova_vaga.criada_por = request.user

            nova_vaga.save()
            messages.success(request, f"Vaga '{nova_vaga.titulo}' salva com sucesso!")
            return redirect('gestao_vagas')
    else:
        form = VagaForm(instance=vaga)

    return render(request, 'rh/form_vaga.html', {'form': form, 'titulo_pagina': titulo_pagina, 'vaga': vaga})


@login_required(login_url='/login/')
def solicitar_abertura_vaga(request):
    if request.method == 'POST':
        form = SolicitacaoVagaForm(request.POST)
        if form.is_valid():
            solicitacao = form.save(commit=False)
            solicitacao.solicitante = request.user
            solicitacao.save()

            messages.success(request, "Solicitação enviada! O RH analisará o pedido em breve.")
            return redirect('home')
    else:
        form = SolicitacaoVagaForm()

    return render(request, 'rh/solicitar_vaga.html', {'form': form})


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def listar_solicitacoes(request):
    """
    O QUE FAZ: Painel do RH para ver todos os pedidos de vagas dos gestores.
    ENGENHARIA: Usamos Case/When para forçar o banco de dados a colocar o status
    'PENDENTE' sempre no topo da tabela, agilizando a vida do RH.
    """
    # Ordenação customizada: Pendentes = 0, Aprovadas = 1, Reprovadas = 2
    solicitacoes = SolicitacaoVaga.objects.all().order_by(
        Case(
            When(status='PENDENTE', then=Value(0)),
            When(status='APROVADA', then=Value(1)),
            When(status='REPROVADA', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        '-data_solicitacao'  # Critério de desempate: Mais recentes primeiro
    )

    total_pendentes = solicitacoes.filter(status='PENDENTE').count()

    return render(request, 'rh/listar_solicitacoes.html', {
        'solicitacoes': solicitacoes,
        'total_pendentes': total_pendentes
    })


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def detalhe_solicitacao(request, pk):
    """
    Abre o pedido detalhado do gestor para o RH ler e dar o parecer (Aprovar/Reprovar).
    """
    solicitacao = get_object_or_404(SolicitacaoVaga, pk=pk)

    if request.method == 'POST':
        novo_status = request.POST.get('status')
        parecer = request.POST.get('observacoes_rh')

        if novo_status:
            solicitacao.status = novo_status
        if parecer is not None:
            solicitacao.observacoes_rh = parecer

        solicitacao.save()
        messages.success(request, f"Parecer registrado! A solicitação para {solicitacao.nome_vaga} foi atualizada.")

        return redirect('listar_solicitacoes')

    return render(request, 'rh/detalhe_solicitacao.html', {'solicitacao': solicitacao})


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def listar_pesquisas(request):
    pesquisas = PesquisaDemissional.objects.all().order_by('-data_geracao')

    if request.GET.get('export_csv') == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pesquisas_demissionais.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')


        writer.writerow([
            'Ex-Colaborador', 'Setor', 'Data Geracao', 'Tempo Casa', 'Periodo Saida', 'Tipo Demissao',
            'Motivo Saida', 'Nota Lideranca', 'Nota Oportunidade', 'Nota Reconhecimento',
            'Nota Clima', 'NPS (Recomendacao)', 'O que faria diferente'
        ])

        for p in pesquisas:
            if getattr(p, 'respondida', False) or p.nota_lideranca:
                writer.writerow([
                    p.ex_funcionario_nome, p.get_setor_display(),
                    p.data_geracao.strftime("%d/%m/%Y %H:%M") if p.data_geracao else '',
                    p.tempo_casa, p.periodo_saida, p.tipo_demissao,
                    p.motivo_saida, p.nota_lideranca, p.nota_oportunidade, p.nota_reconhecimento,
                    p.nota_clima, p.nota_recomendacao, p.diferente
                ])
        return response

    total_geradas = pesquisas.count()
    total_respondidas = pesquisas.exclude(nota_lideranca__isnull=True).count()

    context = {
        'pesquisas': pesquisas,
        'total_geradas': total_geradas,
        'total_respondidas': total_respondidas,
    }

    return render(request, 'rh/listar_pesquisas.html', context)


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def gerar_pesquisa(request):

    if request.method == 'POST':
        form = PesquisaDemissionalGeracaoForm(request.POST)
        if form.is_valid():
            pesquisa = form.save(commit=False)
            pesquisa.gerada_por = request.user
            pesquisa.save()
            messages.success(request, f"Link gerado para {pesquisa.ex_funcionario_nome}.")
            return redirect('listar_pesquisas')

    else:
        form = PesquisaDemissionalGeracaoForm()

    return render(request, 'rh/gerar_pesquisa.html', {'form': form})


def responder_pesquisa(request, uuid_pesquisa):
    """Rota externa acesso via link publico"""
    pesquisa = get_object_or_404(PesquisaDemissional, id_pesquisa=uuid_pesquisa)

    if pesquisa.respondida:
        return render(request, 'rh/pesquisa_ja_respondida.html', {'pesquisa': pesquisa})

    if request.method == 'POST':
        form = PesquisaDemissionalRespostaForm(request.POST, instance=pesquisa)
        if form.is_valid():
            pesquisa = form.save(commit=False)
            pesquisa.respondida = True
            pesquisa.data_resposta = timezone.now()
            pesquisa.save()
            return render(request, 'rh/pesquisa_sucesso.html')
    else:
        form = PesquisaDemissionalRespostaForm()
    return render(request, 'rh/responder_pesquisa.html', {'form': form, 'pesquisa': pesquisa})
