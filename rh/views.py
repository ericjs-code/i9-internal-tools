import csv
import pandas as pd
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponse
from core.decorators import group_required, exige_permissao
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.db.models import Count, Case, When, Value, IntegerField, Q, Sum

from core.utils.utils import convert_hours
from .models import (Vaga, Candidatura, SolicitacaoVaga, PesquisaDemissional,
                     FormularioAdmissional, Funcionario, RegistroAbsenteismo)
from .forms import (CandidaturaForm, VagaForm, SolicitacaoVagaForm,
                    PesquisaDemissionalGeracaoForm, PesquisaDemissionalRespostaForm,
                    FormularioAdmissionalGeracaoForm, FormularioAdmissionalRespostaForm,
                    DependenteAdmissionalFormSet)


def job_list(request):
    vagas = Vaga.objects.filter(ativa=True).order_by('-data_criacao')
    return render(request, 'rh/job_list.html', {'vagas': vagas})


def job_apply(request, pk):
    vaga = get_object_or_404(Vaga, pk=pk, ativa=True)

    if request.method == 'POST':
        form = CandidaturaForm(request.POST, request.FILES)

        if form.is_valid():
            candidatura = form.save(commit=False)
            candidatura.vaga = vaga
            candidatura.save()

            messages.success(request, 'CurrÃ­culo enviado com sucesso!')
            return redirect('job_list')
    else:
        form = CandidaturaForm()

    return render(request, 'rh/job_apply.html', {'form': form, 'vaga': vaga})


@login_required(login_url='/login/')
@group_required(['RH'])
def candidate_screening(request):
    """
    Prepara a lista de candidatos e os contadores para a tela inicial do RH
    """
    vaga_id = request.GET.get('vaga')

    vagas = Vaga.objects.all().order_by('-data_criacao')

    if vaga_id:
        candidaturas = Candidatura.objects.filter(vaga_id=vaga_id).order_by('-data_aplicacao')
        vaga_selecionada = get_object_or_404(Vaga, id=vaga_id)
    else:
        candidaturas = Candidatura.objects.all().order_by('-data_aplicacao')
        vaga_selecionada = None

    contagens = Candidatura.objects.aggregate(
        total_novos=Count('id', filter=Q(status=Candidatura.STATUS.NOVO)),
        total_analise=Count('id', filter=Q(status=Candidatura.STATUS.EM_ANALISE)),
        total_entrevistas=Count('id', filter=Q(status=Candidatura.STATUS.ENTREVISTA))
    )

    context = {
        'vagas': vagas,
        'candidaturas': candidaturas,
        'vaga_selecionada': vaga_selecionada,
        'total_novos': contagens['total_novos'],
        'total_analise': contagens['total_analise'],
        'total_entrevistas': contagens['total_entrevistas']
    }

    return render(request, 'rh/candidate_screening.html', context)


@login_required(login_url='/login')
@group_required(['RH'])
def candidate_datail(request, pk):
    """
    Exibe o currÃ­culo de um candidato e permite o usuario mudar de fase (aprovar ou reprovar)
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

        messages.success(request, f'AvaliaÃ§Ã£o de {candidatura.nome_completo} atualizada.')

        return redirect('candidate_datail', pk= candidatura.id)

    return render(request, 'rh/candidate_datail.html', {'candidatura': candidatura})


@login_required(login_url='/login')
@group_required(['RH'])
def job_management(request):
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
    return render(request, 'rh/job_management.html', context)


@login_required(login_url='/login/')
def job_form(request, pk=None):
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
            return redirect('job_management')
    else:
        form = VagaForm(instance=vaga)

    return render(request, 'rh/job_form.html', {'form': form, 'titulo_pagina': titulo_pagina, 'vaga': vaga})


@login_required(login_url='/login/')
def solicitar_abertura_vaga(request):
    if request.method == 'POST':
        form = SolicitacaoVagaForm(request.POST)
        if form.is_valid():
            solicitacao = form.save(commit=False)
            solicitacao.solicitante = request.user
            solicitacao.save()

            messages.success(request, "SolicitaÃ§Ã£o enviada! O RH analisarÃ¡ o pedido em breve.")
            return redirect('home')
    else:
        form = SolicitacaoVagaForm()

    return render(request, 'rh/solicitar_vaga.html', {'form': form})


@login_required(login_url='/login/')
@group_required(['RH'])
def listar_solicitacoes(request):
    """
    O QUE FAZ: Painel do RH para ver todos os pedidos de vagas dos gestores.
    ENGENHARIA: Usamos Case/When para forÃ§ar o banco de dados a colocar o status
    'PENDENTE' sempre no topo da tabela, agilizando a vida do RH.
    """
    # OrdenaÃ§Ã£o customizada: Pendentes = 0, Aprovadas = 1, Reprovadas = 2
    solicitacoes = SolicitacaoVaga.objects.all().order_by(
        Case(
            When(status='PENDENTE', then=Value(0)),
            When(status='APROVADA', then=Value(1)),
            When(status='REPROVADA', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
        '-data_solicitacao'  # CritÃ©rio de desempate: Mais recentes primeiro
    )

    total_pendentes = solicitacoes.filter(status='PENDENTE').count()

    return render(request, 'rh/listar_solicitacoes.html', {
        'solicitacoes': solicitacoes,
        'total_pendentes': total_pendentes
    })


@login_required(login_url='/login/')
@group_required(['RH'])
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
        messages.success(request, f"Parecer registrado! A solicitaÃ§Ã£o para {solicitacao.nome_vaga} foi atualizada.")

        return redirect('listar_solicitacoes')

    return render(request, 'rh/detalhe_solicitacao.html', {'solicitacao': solicitacao})


@login_required(login_url='/login/')
@group_required(['RH'])
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
@group_required(['RH'])
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


def _dependentes_texto(formulario):
    dependentes = []
    for dependente in formulario.dependentes.all():
        data_nascimento = dependente.data_nascimento.strftime('%d/%m/%Y') if dependente.data_nascimento else ''
        dependentes.append(
            f'Nome: {dependente.nome_completo} | Nascimento: {data_nascimento} | '
            f'RG: {dependente.rg} | CPF: {dependente.cpf} | '
            f'Cidade/Estado: {dependente.cidade_estado_nascimento}'
        )
    return ' || '.join(dependentes)


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def listar_formularios_admissionais(request):
    formularios = FormularioAdmissional.objects.select_related('gerado_por').prefetch_related('dependentes').order_by('-data_geracao')

    if request.GET.get('export_csv') == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="formularios_admissionais.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Nome Candidato Interno', 'Data Geracao', 'Gerado Por', 'Status', 'Data Resposta',
            'Nome Completo', 'CPF', 'Funcao Pretendida', 'PIS', 'Numero CTPS', 'Serie CTPS', 'UF CTPS',
            'CEP', 'Endereco', 'Bairro', 'Cidade/Estado', 'Telefone Principal', 'Contato Recado', 'Email',
            'Data Nascimento', 'Estado Nascimento', 'Naturalidade', 'Cor/Raca', 'Grau Instrucao',
            'Nome Mae', 'Nome Pai', 'Numero RG', 'Orgao Expedidor', 'UF RG', 'Data Emissao RG',
            'Titulo Eleitor', 'Zona Eleitoral', 'Secao Eleitoral', 'UF Titulo Eleitor', 'Reservista',
            'NÂº CNH', 'Validade CNH', 'Estado CNH',
            'Estado Civil', 'Possui Dependentes IR', 'Dependentes Texto',
            'Botina', 'Camisa', 'Calca', 'Utiliza Vale Transporte', 'Trajeto Vale Transporte', 'LGPD Consentimento', 'Observacoes RH',
        ])

        for formulario in formularios:
            writer.writerow([
                formulario.candidato_nome_interno,
                formulario.data_geracao.strftime('%d/%m/%Y %H:%M') if formulario.data_geracao else '',
                formulario.gerado_por.get_username() if formulario.gerado_por else '',
                'Respondido' if formulario.respondido else 'Pendente',
                formulario.data_resposta.strftime('%d/%m/%Y %H:%M') if formulario.data_resposta else '',
                formulario.nome_completo,
                formulario.cpf,
                formulario.funcao_pretendida,
                formulario.pis,
                formulario.numero_ctps,
                formulario.serie_ctps,
                formulario.uf_ctps,
                formulario.cep,
                formulario.endereco,
                formulario.bairro,
                formulario.cidade_estado,
                formulario.telefone_principal,
                formulario.contato_recado,
                formulario.email,
                formulario.data_nascimento.strftime('%d/%m/%Y') if formulario.data_nascimento else '',
                formulario.estado_nascimento,
                formulario.naturalidade,
                formulario.get_cor_raca_display() if formulario.cor_raca else '',
                formulario.get_grau_instrucao_display() if formulario.grau_instrucao else '',
                formulario.nome_mae,
                formulario.nome_pai,
                formulario.numero_rg,
                formulario.orgao_expedidor,
                formulario.uf_rg,
                formulario.data_emissao_rg.strftime('%d/%m/%Y') if formulario.data_emissao_rg else '',
                formulario.titulo_eleitor,
                formulario.zona_eleitoral,
                formulario.secao_eleitoral,
                formulario.uf_titulo_eleitor,
                formulario.reservista,
                formulario.numero_cnh,
                formulario.validade_cnh.strftime('%d/%m/%Y') if formulario.validade_cnh else '',
                formulario.estado_cnh,
                formulario.get_estado_civil_display() if formulario.estado_civil else '',
                formulario.get_possui_dependentes_ir_display() if formulario.possui_dependentes_ir else '',
                _dependentes_texto(formulario),
                formulario.botina,
                formulario.camisa,
                formulario.calca,
                formulario.get_utiliza_vale_transporte_display() if formulario.utiliza_vale_transporte else '',
                formulario.trajeto_vale_transporte,
                'Sim' if formulario.lgpd_consentimento else 'Nao',
                formulario.observacoes_rh,
            ])
        return response

    total_gerados = formularios.count()
    total_respondidos = formularios.filter(respondido=True).count()
    total_pendentes = total_gerados - total_respondidos

    context = {
        'formularios': formularios,
        'total_gerados': total_gerados,
        'total_respondidos': total_respondidos,
        'total_pendentes': total_pendentes,
    }
    return render(request, 'rh/listar_formularios_admissionais.html', context)


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def gerar_formulario_admissional(request):
    if request.method == 'POST':
        form = FormularioAdmissionalGeracaoForm(request.POST)
        if form.is_valid():
            formulario = form.save(commit=False)
            formulario.gerado_por = request.user
            formulario.respondido = False
            formulario.save()
            messages.success(request, f'Link admissional gerado para {formulario.candidato_nome_interno}.')
            return redirect('listar_formularios_admissionais')
    else:
        form = FormularioAdmissionalGeracaoForm()

    return render(request, 'rh/gerar_formulario_admissional.html', {'form': form})


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def detalhe_formulario_admissional(request, uuid_formulario):
    formulario = get_object_or_404(
        FormularioAdmissional.objects.select_related('gerado_por').prefetch_related('dependentes'),
        id_formulario=uuid_formulario
    )
    return render(request, 'rh/detalhe_formulario_admissional.html', {'formulario': formulario})


def responder_formulario_admissional(request, uuid_formulario):
    """Rota externa de acesso via link publico protegido por UUID."""
    formulario = get_object_or_404(FormularioAdmissional, id_formulario=uuid_formulario)

    if formulario.respondido:
        return render(request, 'rh/formulario_admissional_ja_respondido.html', {'formulario': formulario})

    if request.method == 'POST':
        form = FormularioAdmissionalRespostaForm(request.POST, instance=formulario)
        formset = DependenteAdmissionalFormSet(request.POST, instance=formulario)

        if form.is_valid():
            possui_dependentes = form.cleaned_data.get('possui_dependentes_ir') == 'SIM'
            formset_valido = formset.is_valid() if possui_dependentes else True
            dependentes_validos = []

            if formset_valido and possui_dependentes:
                dependentes_validos = [
                    form_dependente for form_dependente in formset.forms
                    if form_dependente.cleaned_data
                    and not form_dependente.cleaned_data.get('DELETE')
                    and form_dependente.cleaned_data.get('nome_completo')
                ]

            if possui_dependentes and not formset_valido:
                pass
            elif possui_dependentes and not dependentes_validos:
                form.add_error('possui_dependentes_ir', 'Informe pelo menos 1 dependente completo.')
            else:
                with transaction.atomic():
                    formulario_bloqueado = FormularioAdmissional.objects.select_for_update().get(id_formulario=uuid_formulario)
                    if formulario_bloqueado.respondido:
                        return render(request, 'rh/formulario_admissional_ja_respondido.html', {'formulario': formulario_bloqueado})

                    formulario_salvo = form.save(commit=False)
                    formulario_salvo.respondido = True
                    formulario_salvo.data_resposta = timezone.now()
                    formulario_salvo.save()

                    if possui_dependentes:
                        formset.instance = formulario_salvo
                        formset.save()
                    else:
                        formulario_salvo.dependentes.all().delete()

                return render(request, 'rh/formulario_admissional_sucesso.html')
    else:
        form = FormularioAdmissionalRespostaForm(instance=formulario)
        formset = DependenteAdmissionalFormSet(instance=formulario)

    return render(request, 'rh/responder_formulario_admissional.html', {
        'form': form,
        'formset': formset,
        'formulario': formulario,
    })


@login_required(login_url='/login/')
@group_required(['RH'])
def dashboard_rh(request):
    ano_atual_sistema = timezone.now().year
    try:
        ano_atual = int(request.GET.get('ano', ano_atual_sistema))
    except ValueError:
        ano_atual = ano_atual_sistema

    data_inicio_ano = f"{ano_atual}-01-01"

    try:
        mes_filtro = int(request.GET.get('mes', 0))
    except ValueError:
        mes_filtro = 0


    # ROTATIVIDADE (TURNOVER)
    total_distinto = Funcionario.objects.filter(
        data_demissao__isnull=True
    ).values('nome_completo').distinct().count()

    admissoes_ano = Funcionario.objects.filter(
        data_admissao__year = ano_atual
    ).count()

    desligamentos_ano = Funcionario.objects.filter(
        data_demissao__year = ano_atual
    ).count()

    colaboradores_inicio = Funcionario.objects.filter(
        Q(data_demissao__isnull=True) | Q(data_demissao__gte=data_inicio_ano),
        data_admissao__lt=data_inicio_ano
    ).count()

    colaboradores_fim = colaboradores_inicio + admissoes_ano - desligamentos_ano

    media_colab = (colaboradores_inicio + colaboradores_fim) / 2
    turnover_geral = 0.0
    if media_colab > 0:
        turnover_geral = ((admissoes_ano + desligamentos_ano) / 2) / media_colab


    # FUNIL DE CONTRATAÃ‡Ã•ES
    # total de vagas criadas no ano
    total_vagas = Vaga.objects.filter(
        data_criacao__year=ano_atual
    ).count()

    # total de candidaturas recebidas no ano
    cvs_recebidos = Candidatura.objects.filter(
        data_aplicacao__year=ano_atual
    ).count()

    # Total de candidatos em processo
    em_processo = Candidatura.objects.filter(
        data_aplicacao__year=ano_atual,
        status__in=[Candidatura.STATUS.EM_ANALISE, Candidatura.STATUS.ENTREVISTA]
    ).count()

    contratados = Candidatura.objects.filter(
        data_aplicacao__year=ano_atual,
        status=Candidatura.STATUS.APROVADO
    ).count()

    vagas_abertas = Vaga.objects.filter(
        data_criacao__year=ano_atual,
        ativa=True
    ).count()


    # ABSENTEÃSMO
    registros_ponto_ano = RegistroAbsenteismo.objects.filter(data_referencia__year=ano_atual)

    if mes_filtro > 0:
        registros_ponto_query = registros_ponto_ano.filter(data_referencia__month=mes_filtro)

    agregado_ponto = registros_ponto_ano.aggregate(
        soma_faltas=Sum('horas_falta'),
        soma_extras=Sum('horas_extras')
    )

    tempo_faltas = agregado_ponto['soma_faltas']
    total_horas_falta = int(tempo_faltas.total_seconds() / 3600) if tempo_faltas else 0

    tempo_extras = agregado_ponto['soma_extras']
    total_horas_extra =  int(tempo_extras.total_seconds() / 3600) if tempo_extras else 0

    media_faltas_colab = round(total_horas_falta / total_distinto, 1) if total_distinto else 0


    context = {
        'mes_filtro': mes_filtro,
        'ano': ano_atual,
        'total_funcionarios': total_distinto,
        'admissoes': admissoes_ano,
        'desligamento': desligamentos_ano,
        'colaboradores_inicio': colaboradores_inicio,
        'turnover_geral': round(turnover_geral * 100, 2),
        'contratados': contratados,
        'em_processo': em_processo,
        'cvs_recebidos': cvs_recebidos,
        'total_vagas': total_vagas,
        'vagas_abertas': vagas_abertas,
        'total_horas_falta': total_horas_falta,
        'total_horas_extra': total_horas_extra,
        'media_faltas_colab': media_faltas_colab,
    }

    return render(request, 'rh/dashboard.html', context)


@login_required(login_url='/login/')
@group_required(['RH'])
def importar_base_rh(request):
    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo_excel')

        if not arquivo:
            messages.error(request, 'Por favor, selecione um arquivo.')
            return redirect('importar_base_rh')

        if not arquivo.name.endswith(('.xls', '.xlsx')):
            messages.error(request, 'Formato invÃ¡lido. Envie um arquivo Excel (.xls ou .xlsx).')
            return redirect('importar_base_rh')

        try:
            df = pd.read_excel(arquivo)
            df = df.replace({pd.NA: None, float('nan'): None, 'NaT': None})

            df['DescriÃ§Ã£o Dpto'] = df['DescriÃ§Ã£o Dpto'].str.replace(' ', '_', regex=False).str.replace('-', '', regex=False)
            df['AdmissÃ£o'] = pd.to_datetime(df['AdmissÃ£o'], errors='coerce', dayfirst=True)
            df['Data DemissÃ£o'] = pd.to_datetime(df['Data DemissÃ£o'], errors='coerce', dayfirst=True)
            df['AdmissÃ£o'] = df['AdmissÃ£o'].dt.strftime('%Y-%m-%d')
            df['Data DemissÃ£o'] = df['Data DemissÃ£o'].dt.strftime('%Y-%m-%d')
            df = df.replace({
                pd.NA: None,
                float('nan'): None,
                'NaT': None,
                'NaN': None,
                'nan': None
            })
            df['CPF'] = df['CPF'].astype(str).str.replace(r'\D', '', regex=True)
            mapa_setor = {
                'ADMINISTRATIVO': 'AD', 'COMERCIAL': 'CO', 'COMPRAS': 'CM',
                'DIRETORIA': 'DI', 'FINANCEIRO': 'FI', 'OBRAS': 'OB',
                'OBRA_MOSAIC': 'OM', 'OBRA_TIMAC': 'OT', 'PLANEJAMENTO_PROCESSO_E_QUALIDADE': 'PP',
                'PRAF_INDUSTRIAL_LTDA': 'PR', 'PRODUÃ‡ÃƒO': 'PD', 'PROJETOS': 'PJ',
                'RECURSOS_HUMANOS': 'RH', 'Sede_ADM': 'SA', 'TECNOLOGIA_DA_INFORMAÃ‡AO': 'TI',
            }

            sucesso = 0

            for index, row in df.iterrows():
                matricula_excel = str(row['CÃ³d Epr']).strip()
                if matricula_excel.lower() in ['nan', 'none', '']:
                    matricula_excel = None
                cpf_excel = str(row['CPF']).replace('.0', '').strip()
                if not cpf_excel or cpf_excel.lower() in ['nan', 'none', '']:
                    if matricula_excel:
                        cpf_excel = f"SEM-CPF-{matricula_excel}"
                    else:
                        continue
                nome_excel = row['Nome']
                salario_excel = row['SalÃ¡rio']
                situacao_excel = str(row['SituaÃ§Ã£o']).strip().upper()
                data_demissao_excel = row['Data DemissÃ£o']
                grau_instrucao_excel = row['Grau instruÃ§Ã£o']
                sexo_excel = row['Sexo']
                dpto_excel = row['DescriÃ§Ã£o Dpto']
                desc_cargo_excel = row['DescriÃ§Ã£o cargo']
                admissao = row['AdmissÃ£o']
                sigla_setor = mapa_setor.get(row['DescriÃ§Ã£o Dpto'], 'CA')
                sigla_situacao = ''
                if situacao_excel == 'DEMITIDO':
                    sigla_situacao = 'DM'
                else:
                    sigla_situacao = 'AT'

                Funcionario.objects.update_or_create(
                    cpf=cpf_excel,
                    defaults={
                        'nome_completo': nome_excel,
                        'situacao': sigla_situacao,
                        'setor': sigla_setor,
                        'data_admissao': admissao,
                        'data_demissao': data_demissao_excel if pd.notnull(data_demissao_excel) else None,
                        'cargo': desc_cargo_excel,
                        'salario': salario_excel,
                        'matricula': str(row['CÃ³d Epr']).strip()
                    }
                )

                sucesso += 1

            messages.success(request, f'Base atualizada com sucesso! {sucesso} registros processados.')
            return redirect('dashboard_rh')

        except Exception as e:
            messages.error(request, f'Erro ao processar o arquivo: {str(e)}')
            return redirect('importar_base_rh')

    return render(request, 'rh/importar_base.html')


@login_required(login_url='/login/')
@group_required(['RH'])
def importar_ponto_rh(request):

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo_csv')

        data_referencia_form = request.POST.get('data_referencia')

        if not arquivo or not data_referencia_form:
            messages.error(request, 'Por favor, selecione o arquivo e a data de referÃªncia.')
            return redirect('importar_ponto_rh')

        # TODO 1: Valide se o arquivo termina com '.csv' (Se nÃ£o, retorne um erro igual na outra view)
        if not arquivo:
            messages.error(request, 'Por favor, selecione um arquivo.')
            return redirect('importar_ponto_rh')

        if not arquivo.name.lower().endswith('.csv'):
            messages.error(request, 'Formato invÃ¡lido. Envie um arquivo CSV (.csv).')
            return redirect('importar_ponto_rh')

        try:
            # TODO 2: Leia o CSV usando os mesmos parÃ¢metros de sucesso que descobrimos no script
            df =  pd.read_csv(arquivo, sep=',', encoding='utf-8-sig', dtype=str)
            df.columns = df.columns.str.strip()
            sucesso = 0
            erros = 0

            for index, row in df.iterrows():
                matricula_excel = str(row['Cod Epr']).replace('.0', '').strip()

                funcionario_obj = Funcionario.objects.filter(
                    matricula=matricula_excel).first()  # Busca o funcionario no banco pela matricula
                if not funcionario_obj:
                    erros += 1
                    continue

                horas_normais_convertidas =convert_hours(row['Total Normais'])
                horas_faltas_convertidas =convert_hours(row['Falta e Atraso'])
                horas_extras_convertidas =convert_hours(row['Extra Diurna'])
                abono_convertido =convert_hours(row['Abono'])

                RegistroAbsenteismo.objects.update_or_create(
                    funcionario=funcionario_obj,
                    data_referencia=data_referencia_form,
                    defaults={
                        'horas_normais': horas_normais_convertidas,
                        'horas_falta': horas_faltas_convertidas,
                        'horas_extras': horas_extras_convertidas,
                        'abono': abono_convertido
                    }
                )

                sucesso += 1

            messages.success(request,
                             f'Ponto importado com sucesso! {sucesso} registros salvos. {erros} nÃ£o encontrados.')
            return redirect('dashboard_rh')

        except Exception as e:
            messages.error(request, f'Erro ao processar o ponto: {str(e)}')
            return redirect('importar_ponto_rh')

    return render(request, 'rh/importar_ponto.html')

