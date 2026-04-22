import csv
import pandas as pd
from datetime import timedelta
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponse
from core.decorators import exige_permissao
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Count, Case, When, Value, IntegerField, Q, Sum

from core.utils.utils import converter_horas
from .models import (Vaga, Candidatura, SolicitacaoVaga, PesquisaDemissional,
                     Funcionario, RegistroAbsenteismo)
from .forms import (CandidaturaForm, VagaForm, SolicitacaoVagaForm,
                    PesquisaDemissionalGeracaoForm, PesquisaDemissionalRespostaForm)


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


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def triagem_rh(request):
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

    return render(request, 'rh/triagem_rh.html', context)


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


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def dashboard_rh(request):
    ano_atual = timezone.now().year
    data_inicio_ano = f"{ano_atual}-01-01"


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


    # FUNIL DE CONTRATAÇÕES
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


    # ABSENTEÍSMO
    registros_ponto_ano = RegistroAbsenteismo.objects.filter(data_referencia__year=ano_atual)

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
@exige_permissao(['rh'])
def importar_base_rh(request):
    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo_excel')

        if not arquivo:
            messages.error(request, 'Por favor, selecione um arquivo.')
            return redirect('importar_base_rh')

        if not arquivo.name.endswith(('.xls', '.xlsx')):
            messages.error(request, 'Formato inválido. Envie um arquivo Excel (.xls ou .xlsx).')
            return redirect('importar_base_rh')

        try:
            df = pd.read_excel(arquivo)
            df = df.replace({pd.NA: None, float('nan'): None, 'NaT': None})

            df['Descrição Dpto'] = df['Descrição Dpto'].str.replace(' ', '_', regex=False).str.replace('-', '', regex=False)
            df['Admissão'] = pd.to_datetime(df['Admissão'], errors='coerce', dayfirst=True)
            df['Data Demissão'] = pd.to_datetime(df['Data Demissão'], errors='coerce', dayfirst=True)
            df['Admissão'] = df['Admissão'].dt.strftime('%Y-%m-%d')
            df['Data Demissão'] = df['Data Demissão'].dt.strftime('%Y-%m-%d')
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
                'PRAF_INDUSTRIAL_LTDA': 'PR', 'PRODUÇÃO': 'PD', 'PROJETOS': 'PJ',
                'RECURSOS_HUMANOS': 'RH', 'Sede_ADM': 'SA', 'TECNOLOGIA_DA_INFORMAÇAO': 'TI',
            }

            sucesso = 0

            for index, row in df.iterrows():
                matricula_excel = str(row['Cód Epr']).strip()
                if matricula_excel.lower() in ['nan', 'none', '']:
                    matricula_excel = None
                cpf_excel = str(row['CPF']).replace('.0', '').strip()
                if not cpf_excel or cpf_excel.lower() in ['nan', 'none', '']:
                    if matricula_excel:
                        cpf_excel = f"SEM-CPF-{matricula_excel}"
                    else:
                        continue
                nome_excel = row['Nome']
                salario_excel = row['Salário']
                situacao_excel = str(row['Situação']).strip().upper()
                data_demissao_excel = row['Data Demissão']
                grau_instrucao_excel = row['Grau instrução']
                sexo_excel = row['Sexo']
                dpto_excel = row['Descrição Dpto']
                desc_cargo_excel = row['Descrição cargo']
                admissao = row['Admissão']
                sigla_setor = mapa_setor.get(row['Descrição Dpto'], 'CA')
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
                        'matricula': str(row['Cód Epr']).strip()
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
@exige_permissao(['rh'])
def importar_ponto_rh(request):

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo_csv')

        data_referencia_form = request.POST.get('data_referencia')

        if not arquivo or not data_referencia_form:
            messages.error(request, 'Por favor, selecione o arquivo e a data de referência.')
            return redirect('importar_ponto_rh')

        # TODO 1: Valide se o arquivo termina com '.csv' (Se não, retorne um erro igual na outra view)
        if not arquivo:
            messages.error(request, 'Por favor, selecione um arquivo.')
            return redirect('importar_ponto_rh')

        if not arquivo.name.lower().endswith('.csv'):
            messages.error(request, 'Formato inválido. Envie um arquivo CSV (.csv).')
            return redirect('importar_ponto_rh')

        try:
            # TODO 2: Leia o CSV usando os mesmos parâmetros de sucesso que descobrimos no script
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

                horas_normais_convertidas =converter_horas(row['Total Normais'])
                horas_faltas_convertidas =converter_horas(row['Falta e Atraso'])
                horas_extras_convertidas =converter_horas(row['Extra Diurna'])
                abono_convertido =converter_horas(row['Abono'])

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
                             f'Ponto importado com sucesso! {sucesso} registros salvos. {erros} não encontrados.')
            return redirect('dashboard_rh')

        except Exception as e:
            messages.error(request, f'Erro ao processar o ponto: {str(e)}')
            return redirect('importar_ponto_rh')

    return render(request, 'rh/importar_ponto.html')