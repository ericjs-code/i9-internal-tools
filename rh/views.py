import csv
import re
import unicodedata
from collections import Counter
from datetime import timedelta
from html import escape
from pathlib import Path
import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.contrib import messages
from django.http import HttpResponse
from core.decorators import group_required, exige_permissao
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.db.models import Avg, Count, Case, When, Value, IntegerField, Q, Sum, Prefetch
from django.views.decorators.http import require_POST
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import SetorOrganizacional
from core.services.permissoes_organizacionais import (
    setores_gerenciados_por,
    usuario_tem_acesso_global,
    usuarios_avaliaveis_para,
    usuarios_visiveis_para,
)
from core.utils.utils import convert_hours
from rh.services.avaliacoes_desempenho import (
    avaliacoes_visiveis_para,
    pode_criar_avaliacao,
    pode_dar_ciencia_colaborador,
    pode_dar_ciencia_gestor,
    pode_editar_avaliacao,
    pode_visualizar_resultado_avaliacao,
    preencher_snapshot_avaliacao,
)
from .models import (Vaga, Candidatura, SolicitacaoVaga, PesquisaDemissional,
                     FormularioAdmissional, Funcionario, RegistroAbsenteismo,
                     AvaliacaoDesempenho, NotaCompetenciaDesempenho,
                     CompetenciaDesempenho, CicloAvaliacaoDesempenho)
from .forms import (CandidaturaForm, VagaForm, SolicitacaoVagaForm,
                    PesquisaDemissionalGeracaoForm, PesquisaDemissionalRespostaForm,
                    FormularioAdmissionalGeracaoForm, FormularioAdmissionalRespostaForm,
                    DependenteAdmissionalFormSet, AvaliacaoDesempenhoForm,
                    NotasCompetenciasDesempenhoForm)


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
    _expirar_pesquisas_demissionais_vencidas()
    pesquisas = PesquisaDemissional.objects.all().order_by('-data_geracao')

    if request.GET.get('export_csv') == '1':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="pesquisas_demissionais.csv"'
        response.write(u'\ufeff'.encode('utf8'))

        writer = csv.writer(response, delimiter=';')


        writer.writerow([
            'Ex-Colaborador', 'Setor', 'Data Geracao', 'Status', 'Data Expiracao', 'Tempo Casa', 'Periodo Saida', 'Tipo Demissao',
            'Motivo Saida', 'Nota Lideranca', 'Nota Oportunidade', 'Nota Reconhecimento',
            'Nota Clima', 'NPS (Recomendacao)', 'O que faria diferente'
        ])

        for p in pesquisas:
            writer.writerow([
                p.ex_funcionario_nome, p.get_setor_display(),
                p.data_geracao.strftime("%d/%m/%Y %H:%M") if p.data_geracao else '',
                p.get_status_display(),
                timezone.localtime(p.data_expiracao).strftime("%d/%m/%Y %H:%M") if p.data_expiracao else '',
                p.tempo_casa, p.periodo_saida, p.get_tipo_demissao_display(),
                p.motivo_saida, p.nota_lideranca, p.nota_oportunidade, p.nota_reconhecimento,
                p.nota_clima, p.nota_recomendacao, p.diferente
            ])
        return response

    total_geradas = pesquisas.count()
    total_respondidas = pesquisas.filter(status=PesquisaDemissional.STATUS.RESPONDIDA).count()
    total_expiradas = pesquisas.filter(status=PesquisaDemissional.STATUS.EXPIRADA).count()

    context = {
        'pesquisas': pesquisas,
        'total_geradas': total_geradas,
        'total_respondidas': total_respondidas,
        'total_expiradas': total_expiradas,
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
            pesquisa.status = PesquisaDemissional.STATUS.PENDENTE
            pesquisa.data_expiracao = timezone.now() + timedelta(days=15)
            pesquisa.save()
            messages.success(request, f"Link gerado para {pesquisa.ex_funcionario_nome}.")
            return redirect('listar_pesquisas')

    else:
        form = PesquisaDemissionalGeracaoForm()

    return render(request, 'rh/gerar_pesquisa.html', {'form': form})


def responder_pesquisa(request, uuid_pesquisa):
    """Rota externa acesso via link publico"""
    pesquisa = get_object_or_404(PesquisaDemissional, id_pesquisa=uuid_pesquisa)
    status_anterior = pesquisa.status
    pesquisa.atualizar_status_expiracao()
    if pesquisa.status != status_anterior:
        pesquisa.save(update_fields=['status'])

    if pesquisa.status == PesquisaDemissional.STATUS.EXPIRADA:
        return render(request, 'rh/pesquisa_expirada.html', {'pesquisa': pesquisa})

    if pesquisa.respondida or pesquisa.status == PesquisaDemissional.STATUS.RESPONDIDA:
        return render(request, 'rh/pesquisa_ja_respondida.html', {'pesquisa': pesquisa})

    if request.method == 'POST':
        form = PesquisaDemissionalRespostaForm(request.POST, instance=pesquisa)
        if form.is_valid():
            pesquisa = form.save(commit=False)
            pesquisa.atualizar_status_expiracao()
            if pesquisa.status == PesquisaDemissional.STATUS.EXPIRADA:
                pesquisa.save(update_fields=['status'])
                return render(request, 'rh/pesquisa_expirada.html', {'pesquisa': pesquisa})
            pesquisa.respondida = True
            pesquisa.status = PesquisaDemissional.STATUS.RESPONDIDA
            pesquisa.data_resposta = timezone.now()
            pesquisa.save()
            return render(request, 'rh/pesquisa_sucesso.html')
    else:
        form = PesquisaDemissionalRespostaForm()
    return render(request, 'rh/responder_pesquisa.html', {'form': form, 'pesquisa': pesquisa})


@login_required(login_url='/login/')
@group_required(['RH'])
@require_POST
def gerar_novo_link_pesquisa_demissional(request, uuid_pesquisa):
    pesquisa = get_object_or_404(PesquisaDemissional, id_pesquisa=uuid_pesquisa)
    status_anterior = pesquisa.status
    pesquisa.atualizar_status_expiracao()
    if pesquisa.status != status_anterior:
        pesquisa.save(update_fields=['status'])

    if not pesquisa.pode_gerar_novo_link:
        messages.warning(request, 'Novo link só pode ser gerado para pesquisa expirada.')
        return redirect('listar_pesquisas')

    PesquisaDemissional.objects.create(
        gerada_por=request.user,
        status=PesquisaDemissional.STATUS.PENDENTE,
        data_expiracao=timezone.now() + timedelta(days=15),
        pesquisa_origem=pesquisa,
        ex_funcionario_nome=pesquisa.ex_funcionario_nome,
        setor=pesquisa.setor,
        tipo_demissao=pesquisa.tipo_demissao,
        periodo_saida=pesquisa.periodo_saida,
        tempo_casa=pesquisa.tempo_casa,
    )
    messages.success(request, 'Novo link gerado com sucesso. O novo prazo de resposta expira em 15 dias.')
    return redirect('listar_pesquisas')


def _expirar_pesquisas_demissionais_vencidas():
    PesquisaDemissional.objects.filter(
        status=PesquisaDemissional.STATUS.PENDENTE,
        data_expiracao__lt=timezone.now(),
    ).update(status=PesquisaDemissional.STATUS.EXPIRADA)


def _dependentes_texto(formulario):
    dependentes = []
    for dependente in formulario.dependentes.all():
        data_nascimento = dependente.data_nascimento.strftime('%d/%m/%Y') if dependente.data_nascimento else ''
        dependentes.append(
            f'Nome: {dependente.nome_completo} | Grau parentesco: {dependente.get_grau_parentesco_display() if dependente.grau_parentesco else ""} | '
            f'Nascimento: {data_nascimento} | '
            f'RG: {dependente.rg} | CPF: {dependente.cpf} | '
            f'Cidade/Estado: {dependente.cidade_estado_nascimento}'
        )
    return ' || '.join(dependentes)


def _valor_pdf(valor):
    return valor if valor not in [None, ''] else '-'


def _nome_arquivo_formulario(formulario):
    nome = formulario.nome_completo or formulario.candidato_nome_interno or 'COLABORADOR'
    cpf = re.sub(r'\D', '', formulario.cpf or '')
    nome = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode('ascii')
    nome = re.sub(r'[^A-Za-z0-9]+', '_', nome).strip('_').upper()
    return f'formulario_admissional_{nome}_{cpf}.pdf'


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
            'CEP', 'Endereco', 'Bairro', 'Cidade/Estado', 'Telefone Principal', 'Telefone para recado',
            'Nome do contato para recado', 'Grau de parentesco do contato para recado', 'Email',
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
                formulario.nome_contato_recado,
                formulario.get_grau_parentesco_contato_recado_display() if formulario.grau_parentesco_contato_recado else '',
                formulario.email,
                formulario.data_nascimento.strftime('%d/%m/%Y') if formulario.data_nascimento else '',
                formulario.get_estado_nascimento_display() if formulario.estado_nascimento else '',
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


@login_required(login_url='/login/')
@exige_permissao(['rh'])
def exportar_formulario_admissional_pdf(request, uuid_formulario):
    formulario = get_object_or_404(
        FormularioAdmissional.objects.select_related('gerado_por').prefetch_related('dependentes'),
        id_formulario=uuid_formulario
    )

    if not formulario.respondido:
        messages.error(request, 'Só é possível exportar PDF de formulário respondido.')
        return redirect('detalhe_formulario_admissional', uuid_formulario=formulario.id_formulario)

    response = HttpResponse(content_type='application/pdf')
    filename = _nome_arquivo_formulario(formulario)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TituloI9', parent=styles['Title'], alignment=TA_CENTER, fontSize=16, spaceAfter=12))
    styles.add(ParagraphStyle(name='SecaoI9', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#141C3C'), spaceBefore=10, spaceAfter=6))
    normal = styles['BodyText']
    elementos = []

    logo_path = Path(settings.BASE_DIR) / 'static' / 'img' / 'logo.jpg'
    if logo_path.exists():
        elementos.append(Image(str(logo_path), width=3.0 * cm, height=1.6 * cm))
        elementos.append(Spacer(1, 0.2 * cm))

    elementos.append(Paragraph('FORMULÁRIO ADMISSIONAL', styles['TituloI9']))

    def data_hora(valor):
        return timezone.localtime(valor).strftime('%d/%m/%Y %H:%M') if valor else '-'

    def data(valor):
        return valor.strftime('%d/%m/%Y') if valor else '-'

    def add_section(titulo, linhas):
        elementos.append(Paragraph(titulo, styles['SecaoI9']))
        table_data = [
            [Paragraph(f'<b>{escape(str(label))}</b>', normal), Paragraph(escape(str(_valor_pdf(valor))), normal)]
            for label, valor in linhas
        ]
        tabela = Table(table_data, colWidths=[6.0 * cm, 11.0 * cm], hAlign='LEFT')
        tabela.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F2F3F5')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elementos.append(tabela)

    add_section('Cabeçalho', [
        ('Nome do colaborador', formulario.nome_completo),
        ('CPF', formulario.cpf),
        ('Data de resposta', data_hora(formulario.data_resposta)),
        ('Gerado por', request.user.get_username()),
        ('Data de geração', timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')),
    ])
    add_section('Dados Básicos', [
        ('Nome completo', formulario.nome_completo),
        ('CPF', formulario.cpf),
        ('Função pretendida', formulario.funcao_pretendida),
    ])
    add_section('CTPS', [
        ('PIS', formulario.pis),
        ('Número da CTPS', formulario.numero_ctps),
        ('Série CTPS', formulario.serie_ctps),
        ('UF CTPS', formulario.uf_ctps),
    ])
    add_section('Endereço', [
        ('CEP', formulario.cep),
        ('Endereço', formulario.endereco),
        ('Bairro', formulario.bairro),
        ('Cidade/Estado', formulario.cidade_estado),
    ])
    add_section('Contatos', [
        ('Telefone principal', formulario.telefone_principal),
        ('Telefone para recado', formulario.contato_recado),
        ('Nome do contato para recado', formulario.nome_contato_recado),
        ('Grau de parentesco', formulario.get_grau_parentesco_contato_recado_display() if formulario.grau_parentesco_contato_recado else ''),
        ('Endereço de e-mail', formulario.email),
    ])
    add_section('Dados Pessoais', [
        ('Data de nascimento', data(formulario.data_nascimento)),
        ('Estado nascimento', formulario.get_estado_nascimento_display() if formulario.estado_nascimento else ''),
        ('Naturalidade', formulario.naturalidade),
        ('Cor/Raça', formulario.get_cor_raca_display() if formulario.cor_raca else ''),
        ('Grau de instrução', formulario.get_grau_instrucao_display() if formulario.grau_instrucao else ''),
        ('Nome da mãe', formulario.nome_mae),
        ('Nome do pai', formulario.nome_pai),
    ])
    add_section('Documentos', [
        ('Número RG', formulario.numero_rg),
        ('Órgão expedidor', formulario.orgao_expedidor),
        ('UF RG', formulario.uf_rg),
        ('Data emissão RG', data(formulario.data_emissao_rg)),
        ('Título de eleitor', formulario.titulo_eleitor),
        ('Zona eleitoral', formulario.zona_eleitoral),
        ('Seção eleitoral', formulario.secao_eleitoral),
        ('UF título eleitor', formulario.uf_titulo_eleitor),
        ('Reservista', formulario.reservista),
        ('Nº CNH', formulario.numero_cnh),
        ('Validade CNH', data(formulario.validade_cnh)),
        ('Estado CNH', formulario.estado_cnh),
    ])
    add_section('Dados Cônjuge', [('Estado civil', formulario.get_estado_civil_display() if formulario.estado_civil else '')])
    add_section('Dependentes', [
        ('Possui dependentes IR', formulario.get_possui_dependentes_ir_display() if formulario.possui_dependentes_ir else ''),
        ('Dependentes', _dependentes_texto(formulario)),
    ])
    add_section('Uniforme', [
        ('Botina', formulario.botina),
        ('Camisa', formulario.camisa),
        ('Calça', formulario.calca),
    ])
    add_section('Vale Transporte', [
        ('Utiliza vale transporte', formulario.get_utiliza_vale_transporte_display() if formulario.utiliza_vale_transporte else ''),
        ('Trajeto', formulario.trajeto_vale_transporte),
    ])
    add_section('LGPD', [('Consentimento', 'Sim' if formulario.lgpd_consentimento else 'Não')])
    add_section('Controle Interno', [
        ('ID formulário', formulario.id_formulario),
        ('Gerado por', formulario.gerado_por.get_username() if formulario.gerado_por else ''),
        ('Data geração', data_hora(formulario.data_geracao)),
        ('Respondido', 'Sim' if formulario.respondido else 'Não'),
        ('Observações RH', formulario.observacoes_rh),
    ])

    doc.build(elementos)
    return response


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


def _query_avaliacoes_desempenho():
    return AvaliacaoDesempenho.objects.select_related(
        'avaliado',
        'avaliada_por',
        'usuario_ciencia_gestor',
        'usuario_ciencia_colaborador',
    ).prefetch_related(
        Prefetch(
            'notas',
            queryset=NotaCompetenciaDesempenho.objects.select_related('competencia').order_by(
                'competencia__ordem',
                'competencia__nome',
            )
        )
    )


def _aplicar_filtros_avaliacoes_desempenho(queryset, params):
    avaliado_id = params.get('filtro_avaliado') or params.get('avaliado') or params.get('funcionario')
    ano = params.get('filtro_ano') or params.get('ano')
    ciclo = params.get('filtro_ciclo') or params.get('ciclo')
    status = params.get('filtro_status') or params.get('status')
    setor = params.get('filtro_setor') or params.get('setor')

    if avaliado_id:
        queryset = queryset.filter(avaliado_id=avaliado_id)
    if ano:
        ano_int = _normalizar_ano_int(ano)
        if ano_int:
            queryset = queryset.filter(ano=ano_int)
    if ciclo:
        queryset = queryset.filter(ciclo=ciclo)
    if status:
        queryset = queryset.filter(status=status)
    if setor:
        queryset = queryset.filter(avaliado__perfil_organizacional__setor_id=setor)

    return queryset


def _funcionarios_avaliacao_queryset(user):
    return usuarios_visiveis_para(user)


def _setores_visiveis_para(user):
    if usuario_tem_acesso_global(user):
        return SetorOrganizacional.objects.filter(ativo=True).order_by('ordem', 'nome')
    return setores_gerenciados_por(user)


def _opcoes_setores_para_template(user):
    return [(setor.id, setor.nome) for setor in _setores_visiveis_para(user)]


def _anos_avaliacoes_desempenho():
    anos = {
        int(ano)
        for ano in AvaliacaoDesempenho.objects
        .exclude(ano__isnull=True)
        .values_list('ano', flat=True)
    }
    anos.add(timezone.now().year)
    return [str(ano) for ano in sorted(anos, reverse=True)]


def _status_choices_avaliacao_interface():
    labels = {
        AvaliacaoDesempenho.STATUS.CIENCIA_PENDENTE: 'Ciencia e Concordancia Pendente',
        AvaliacaoDesempenho.STATUS.CIENCIA_PARCIAL: 'Ciencia e Concordancia Parcial',
        AvaliacaoDesempenho.STATUS.CIENCIA_CONCLUIDA: 'Ciencia e Concordancia Concluida',
    }
    return [
        (valor, labels.get(valor, rotulo))
        for valor, rotulo in AvaliacaoDesempenho.STATUS.choices
    ]


def _salvar_notas_desempenho(avaliacao, notas_limpas):
    notas_existentes = {
        nota.competencia_id: nota
        for nota in avaliacao.notas.select_for_update().all()
    }

    for item in notas_limpas:
        competencia = item['competencia']
        nota = notas_existentes.get(competencia.id) or NotaCompetenciaDesempenho(
            avaliacao=avaliacao,
            competencia=competencia,
        )
        nota.nota = item['nota']
        nota.comentario = item['comentario']
        nota.save()


def _preencher_ciclo_avaliacao(avaliacao):
    if avaliacao.ano and avaliacao.ciclo:
        avaliacao.ciclo_avaliacao = CicloAvaliacaoDesempenho.obter_ou_criar(
            avaliacao.ano,
            avaliacao.ciclo,
        )
    return avaliacao


def _dados_dashboard_avaliacao(avaliacao, user=None):
    notas = list(avaliacao.notas.select_related('competencia').order_by('competencia__ordem', 'competencia__nome'))
    media = avaliacao.media
    maior_nota = max((nota.nota for nota in notas), default=None)
    menor_nota = min((nota.nota for nota in notas), default=None)

    pontos_fortes = [nota for nota in notas if nota.nota >= 9]
    pontos_atencao = [nota for nota in notas if nota.nota <= 7]
    acima_media = [nota for nota in notas if media is not None and nota.nota >= media]
    abaixo_media = [nota for nota in notas if media is not None and nota.nota < media]
    historico_avaliacoes = list(
        _query_avaliacoes_desempenho()
        .filter(avaliado=avaliacao.avaliado)
        .order_by('ano', 'ciclo')
    )
    if user:
        historico_avaliacoes = [
            historico
            for historico in historico_avaliacoes
            if pode_visualizar_resultado_avaliacao(user, historico)
        ]
    historico_periodos = [historico.periodo_formatado for historico in historico_avaliacoes]
    competencias_historico = list(CompetenciaDesempenho.objects.filter(ativa=True).order_by('ordem', 'nome'))
    notas_historico = {
        (nota.avaliacao_id, nota.competencia_id): nota.nota
        for historico in historico_avaliacoes
        for nota in historico.notas.all()
    }
    tabela_historico = []
    for competencia in competencias_historico:
        tabela_historico.append({
            'competencia': competencia,
            'valores': [
                notas_historico.get((historico.id, competencia.id), '')
                for historico in historico_avaliacoes
            ],
        })
    medias_historico = [
        {
            'periodo': historico.periodo_formatado,
            'media': float(historico.media or 0),
        }
        for historico in historico_avaliacoes
    ]
    labels_competencias = [nome_curto_competencia(nota.competencia.nome) for nota in notas]
    notas_competencias = [float(nota.nota) for nota in notas]

    pode_editar = pode_editar_avaliacao(user, avaliacao) if user else False
    pode_ciencia_gestor = pode_dar_ciencia_gestor(user, avaliacao) if user else False
    usuario_eh_avaliado = bool(user and user.is_authenticated and avaliacao.avaliado_id == user.id)
    pode_ciencia_colaborador = (
        usuario_eh_avaliado
        and avaliacao.ciencia_gestor
        and not avaliacao.ciencia_colaborador
    )
    colaborador_aguardando_ciencia_gestor = (
        usuario_eh_avaliado
        and not avaliacao.ciencia_gestor
        and not avaliacao.ciencia_colaborador
    )

    return {
        'avaliacao': avaliacao,
        'notas': notas,
        'media': media,
        'maior_nota': maior_nota,
        'menor_nota': menor_nota,
        'total_competencias': len(notas),
        'pontos_fortes': pontos_fortes,
        'pontos_atencao': pontos_atencao,
        'competencias_acima_media': acima_media,
        'competencias_abaixo_media': abaixo_media,
        'chart_labels': labels_competencias,
        'chart_values': notas_competencias,
        'historico_avaliacoes': historico_avaliacoes,
        'historico_periodos': historico_periodos,
        'tabela_historico': tabela_historico,
        'medias_historico': medias_historico,
        'medias_historico_labels': [item['periodo'] for item in medias_historico],
        'medias_historico_values': [item['media'] for item in medias_historico],
        'pode_editar': pode_editar,
        'pode_dar_ciencia_gestor': pode_ciencia_gestor and not avaliacao.ciencia_gestor,
        'pode_dar_ciencia_colaborador': pode_ciencia_colaborador,
        'colaborador_aguardando_ciencia_gestor': colaborador_aguardando_ciencia_gestor,
    }


def nome_curto_competencia(nome):
    nome = nome or ''
    mapa = {
        'Pontualidade/ Assiduidade': 'Pontualidade',
        'Pontualidade/Assiduidade': 'Pontualidade',
        'Iniciativa/Pró-atividade': 'Iniciativa',
        'Iniciativa/Pro-atividade': 'Iniciativa',
        'Relacionamento': 'Relacionamento',
        'Organização': 'Organização',
        'Organizacao': 'Organização',
        'Metas': 'Metas',
        'Qualidade do serviço /Atenção': 'Qualidade',
        'Qualidade do serviço/Atenção': 'Qualidade',
        'Qualidade do servico/Atencao': 'Qualidade',
        'Postura Profissional': 'Postura',
        'Conhecimento / Desenvolvimento profissional': 'Conhecimento',
        'Conhecimento/Desenvolvimento profissional': 'Conhecimento',
        'Liderança': 'Liderança',
        'Lideranca': 'Liderança',
    }
    return mapa.get(nome, nome[:18])


def _valor_pdf(valor):
    if valor is None:
        return '-'
    texto = str(valor).strip()
    return texto if texto else '-'


def _nome_arquivo_avaliacao(avaliacao):
    nome = unicodedata.normalize('NFKD', avaliacao.funcionario_nome)
    nome = nome.encode('ascii', 'ignore').decode('ascii')
    nome = re.sub(r'[^A-Za-z0-9]+', '_', nome).strip('_').lower()
    return f'avaliacao_desempenho_{nome}_{avaliacao.ano_formatado}_{avaliacao.ciclo}.pdf'


def _paragraph(texto, style):
    texto = escape(_valor_pdf(texto)).replace('\n', '<br/>')
    texto = texto.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
    return Paragraph(texto, style)


def _grafico_barras_pdf(notas):
    drawing = Drawing(500, 240)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 70
    chart.height = 135
    chart.width = 420
    chart.data = [[nota.nota for nota in notas]]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 10
    chart.valueAxis.valueStep = 1
    chart.categoryAxis.categoryNames = [
        nome_curto_competencia(nota.competencia.nome)
        for nota in notas
    ]
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.boxAnchor = 'ne'
    chart.categoryAxis.labels.dy = -4
    chart.bars[0].fillColor = colors.HexColor('#FF742E')
    chart.barSpacing = 3
    drawing.add(chart)
    drawing.add(String(35, 15, 'Competencias avaliadas', fontSize=8, fillColor=colors.HexColor('#666666')))
    return drawing


def _grafico_medias_pdf(medias_historico):
    valores = [item['media'] or 0 for item in medias_historico]
    labels = [item['periodo'].split(' - ')[0] for item in medias_historico]
    drawing = Drawing(500, 220)
    chart = VerticalBarChart()
    chart.x = 35
    chart.y = 45
    chart.height = 135
    chart.width = 420
    chart.data = [valores]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 10
    chart.valueAxis.valueStep = 1
    chart.categoryAxis.categoryNames = labels
    chart.bars[0].fillColor = colors.HexColor('#141C3C')
    chart.barSpacing = 4
    drawing.add(chart)
    drawing.add(String(35, 15, 'Evolucao da media por ciclo', fontSize=8, fillColor=colors.HexColor('#666666')))
    return drawing


def _tabela_pdf(linhas, col_widths, header=True):
    tabela = Table(linhas, colWidths=col_widths, repeatRows=1 if header else 0, hAlign='LEFT')
    estilos = [
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#DDDDDD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    if header:
        estilos.extend([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#141C3C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ])
    tabela.setStyle(TableStyle(estilos))
    return tabela


def _nome_usuario_pdf(user):
    if not user:
        return ''
    return user.get_full_name() or user.username


def _formatar_data_hora_pdf(data_hora):
    if not data_hora:
        return ''
    return timezone.localtime(data_hora).strftime('%d/%m/%Y %H:%M')


def _assinatura_gestor_pdf(avaliacao):
    if avaliacao.ciencia_gestor:
        nome = _nome_usuario_pdf(avaliacao.usuario_ciencia_gestor)
        data = _formatar_data_hora_pdf(avaliacao.data_ciencia_gestor)
        return nome or 'Gestor ciente', data
    return '________________________________________', '______________'


def _assinatura_colaborador_pdf(avaliacao):
    if avaliacao.ciencia_colaborador:
        usuario = avaliacao.usuario_ciencia_colaborador or avaliacao.avaliado
        nome = _nome_usuario_pdf(usuario)
        data = _formatar_data_hora_pdf(avaliacao.data_ciencia_colaborador)
        return nome or 'Colaborador ciente', data
    return '________________________________________', '______________'


def _assinaturas_pdf(avaliacao):
    nome_gestor, data_gestor = _assinatura_gestor_pdf(avaliacao)
    nome_colaborador, data_colaborador = _assinatura_colaborador_pdf(avaliacao)
    header_style = ParagraphStyle(
        'AssinaturaHeaderPdf',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
    )
    valor_style = ParagraphStyle(
        'AssinaturaValorPdf',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
    )
    assinaturas = [
        [
            Paragraph('Assinatura Gestor', header_style),
            Paragraph('Data', header_style),
            Paragraph('Assinatura Colaborador', header_style),
            Paragraph('Data', header_style),
        ],
        [
            Paragraph(escape(nome_gestor), valor_style),
            Paragraph(escape(data_gestor), valor_style),
            Paragraph(escape(nome_colaborador), valor_style),
            Paragraph(escape(data_colaborador), valor_style),
        ],
    ]
    tabela = Table(assinaturas, colWidths=[6.0 * cm, 2.2 * cm, 6.0 * cm, 2.2 * cm], rowHeights=[0.7 * cm, 1.2 * cm])
    tabela.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('LINEBELOW', (0, 1), (0, 1), 0.6, colors.HexColor('#333333')),
        ('LINEBELOW', (2, 1), (2, 1), 0.6, colors.HexColor('#333333')),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return tabela


def _ciencia_pdf(avaliacao, normal):
    linhas = [
        [_paragraph('<b>Ciencia e Concordancia do Gestor</b>', normal), _paragraph('Ciente e de acordo' if avaliacao.ciencia_gestor else 'Pendente', normal), _paragraph('<b>Usuario</b>', normal), _paragraph(avaliacao.usuario_ciencia_gestor.get_username() if avaliacao.usuario_ciencia_gestor else '-', normal)],
        [_paragraph('<b>Data/Hora</b>', normal), _paragraph(timezone.localtime(avaliacao.data_ciencia_gestor).strftime('%d/%m/%Y %H:%M') if avaliacao.data_ciencia_gestor else '-', normal), _paragraph('', normal), _paragraph('', normal)],
        [_paragraph('<b>Ciencia e Concordancia do Colaborador</b>', normal), _paragraph('Ciente e de acordo' if avaliacao.ciencia_colaborador else 'Pendente', normal), _paragraph('<b>Usuario</b>', normal), _paragraph(avaliacao.usuario_ciencia_colaborador.get_username() if avaliacao.usuario_ciencia_colaborador else '-', normal)],
        [_paragraph('<b>Data/Hora</b>', normal), _paragraph(timezone.localtime(avaliacao.data_ciencia_colaborador).strftime('%d/%m/%Y %H:%M') if avaliacao.data_ciencia_colaborador else '-', normal), _paragraph('', normal), _paragraph('', normal)],
    ]
    return _tabela_pdf(linhas, [4.2 * cm, 4.5 * cm, 3.0 * cm, 5.7 * cm], header=False)


def _exportar_avaliacoes_desempenho_csv(avaliacoes):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="avaliacoes_desempenho.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    competencias_csv = [
        'Pontualidade/Assiduidade',
        'Iniciativa/Pro-atividade',
        'Relacionamento',
        'Organizacao',
        'Metas',
        'Qualidade do servico/Atencao',
        'Postura Profissional',
        'Conhecimento/Desenvolvimento profissional',
        'Lideranca',
    ]

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'Colaborador', 'Cargo', 'Setor', 'Data Admissao', 'Ano', 'Ciclo', 'Mes Calculado',
        'Periodo', 'Status', 'Media', 'Classificacao', *competencias_csv, 'Comentarios Gerais',
        'Ciencia e Concordancia Gestor', 'Data Ciencia e Concordancia Gestor', 'Usuario Ciencia e Concordancia Gestor',
        'Ciencia e Concordancia Colaborador', 'Data Ciencia e Concordancia Colaborador',
        'Usuario Ciencia e Concordancia Colaborador', 'Data Avaliacao', 'Avaliado Por',
    ])

    for avaliacao in avaliacoes:
        notas_por_ordem = {nota.competencia.ordem: nota.nota for nota in avaliacao.notas.all()}
        writer.writerow([
            avaliacao.funcionario_nome,
            avaliacao.funcionario_cargo,
            avaliacao.funcionario_setor,
            avaliacao.funcionario_data_admissao.strftime('%d/%m/%Y') if avaliacao.funcionario_data_admissao else '',
            avaliacao.ano_formatado,
            avaliacao.ciclo,
            avaliacao.mes_referencia,
            avaliacao.periodo_formatado,
            avaliacao.status_calculado_display,
            str(avaliacao.media).replace('.', ',') if avaliacao.media is not None else '',
            avaliacao.classificacao,
            *[notas_por_ordem.get(ordem, '') for ordem in range(1, 10)],
            avaliacao.comentarios,
            'Sim' if avaliacao.ciencia_gestor else 'Nao',
            avaliacao.data_ciencia_gestor.strftime('%d/%m/%Y %H:%M') if avaliacao.data_ciencia_gestor else '',
            avaliacao.usuario_ciencia_gestor.get_username() if avaliacao.usuario_ciencia_gestor else '',
            'Sim' if avaliacao.ciencia_colaborador else 'Nao',
            avaliacao.data_ciencia_colaborador.strftime('%d/%m/%Y %H:%M') if avaliacao.data_ciencia_colaborador else '',
            avaliacao.usuario_ciencia_colaborador.get_username() if avaliacao.usuario_ciencia_colaborador else '',
            avaliacao.data_avaliacao.strftime('%d/%m/%Y %H:%M') if avaliacao.data_avaliacao else '',
            avaliacao.avaliada_por.get_username() if avaliacao.avaliada_por else '',
        ])

    return response


def _normalizar_ano_int(valor):
    ano_limpo = str(valor or '').replace('.', '').replace(',', '').strip()
    if not ano_limpo.isdigit():
        return None
    try:
        return int(ano_limpo)
    except (TypeError, ValueError):
        return None


def _ano_filtro_avaliacao(parametro, padrao=None):
    padrao = padrao or timezone.now().year
    return _normalizar_ano_int(parametro) or padrao


def _usuarios_sem_avaliacao_context(request):
    ano_atual = timezone.now().year
    if not pode_criar_avaliacao(request.user):
        pendentes_ano = str(ano_atual)
        return {
            'usuarios_sem_avaliacao': [],
            'pendentes_ano': pendentes_ano,
            'pendentes_ciclo': 'A',
            'ano_filtro': pendentes_ano,
            'ciclo_filtro': 'A',
        }

    ano = _ano_filtro_avaliacao(
        request.GET.get('pendentes_ano'),
        ano_atual,
    )
    ciclo = request.GET.get('pendentes_ciclo') or 'A'
    if ciclo not in ['A', 'B']:
        ciclo = 'A'

    usuarios = usuarios_avaliaveis_para(request.user).exclude(
        avaliacoes_recebidas__ano=ano,
        avaliacoes_recebidas__ciclo=ciclo,
    ).select_related('perfil_organizacional__setor')

    pendentes_ano = str(int(ano))
    return {
        'usuarios_sem_avaliacao': usuarios,
        'pendentes_ano': pendentes_ano,
        'pendentes_ciclo': ciclo,
        'ano_filtro': pendentes_ano,
        'ciclo_filtro': ciclo,
    }


@login_required(login_url='/login/')
def listar_avaliacoes_desempenho(request):
    filtro_ano_int = _normalizar_ano_int(request.GET.get('filtro_ano'))
    filtros_avaliacoes = {
        'filtro_avaliado': request.GET.get('filtro_avaliado', ''),
        'filtro_setor': request.GET.get('filtro_setor', ''),
        'filtro_ano': str(filtro_ano_int) if filtro_ano_int else '',
        'filtro_ciclo': request.GET.get('filtro_ciclo', ''),
        'filtro_status': request.GET.get('filtro_status', ''),
    }
    avaliacoes = _aplicar_filtros_avaliacoes_desempenho(
        avaliacoes_visiveis_para(request.user).order_by('-data_avaliacao'),
        filtros_avaliacoes,
    )

    if request.GET.get('export_csv') == '1':
        avaliacoes_exportacao = [
            avaliacao
            for avaliacao in avaliacoes
            if pode_visualizar_resultado_avaliacao(request.user, avaliacao)
        ]
        return _exportar_avaliacoes_desempenho_csv(avaliacoes_exportacao)

    avaliacoes_lista = list(avaliacoes)
    for avaliacao in avaliacoes_lista:
        avaliacao.pode_editar = pode_editar_avaliacao(request.user, avaliacao)
        avaliacao.pode_visualizar_resultado = pode_visualizar_resultado_avaliacao(request.user, avaliacao)
        avaliacao.pode_dar_ciencia_colaborador = (
            avaliacao.avaliado_id == request.user.id
            and avaliacao.ciencia_gestor
            and not avaliacao.ciencia_colaborador
        )
        avaliacao.colaborador_aguardando_ciencia_gestor = (
            avaliacao.avaliado_id == request.user.id
            and not avaliacao.ciencia_gestor
            and not avaliacao.ciencia_colaborador
        )
        avaliacao.ciencia_colaborador_registrada_usuario = (
            avaliacao.avaliado_id == request.user.id
            and avaliacao.ciencia_colaborador
        )
        avaliacao.pode_dar_ciencia_gestor = (
            pode_dar_ciencia_gestor(request.user, avaliacao)
            and not avaliacao.ciencia_gestor
        )

    medias = [
        avaliacao.media
        for avaliacao in avaliacoes_lista
        if avaliacao.pode_visualizar_resultado and avaliacao.media is not None
    ]
    media_geral = round(sum(medias) / len(medias), 2) if medias else None

    context = {
        'avaliacoes': avaliacoes_lista,
        'funcionarios': _funcionarios_avaliacao_queryset(request.user),
        'setores': _opcoes_setores_para_template(request.user),
        'anos': _anos_avaliacoes_desempenho(),
        'status_choices': _status_choices_avaliacao_interface(),
        'ciclo_choices': AvaliacaoDesempenho.CICLO.choices,
        'filtros': filtros_avaliacoes,
        **filtros_avaliacoes,
        'total_avaliacoes': len(avaliacoes_lista),
        'total_finalizadas': sum(1 for avaliacao in avaliacoes_lista if avaliacao.status_calculado == AvaliacaoDesempenho.STATUS.CIENCIA_CONCLUIDA),
        'total_rascunhos': sum(1 for avaliacao in avaliacoes_lista if avaliacao.status_calculado == AvaliacaoDesempenho.STATUS.RASCUNHO),
        'media_geral': media_geral,
        'pode_criar_avaliacao': pode_criar_avaliacao(request.user),
        'pode_criar': pode_criar_avaliacao(request.user),
        'pode_exportar_csv': any(avaliacao.pode_visualizar_resultado for avaliacao in avaliacoes_lista),
    }
    context.update(_usuarios_sem_avaliacao_context(request))
    return render(request, 'rh/listar_avaliacoes_desempenho.html', context)


@login_required(login_url='/login/')
def nova_avaliacao_desempenho(request):
    if not pode_criar_avaliacao(request.user):
        messages.error(request, 'Voce nao possui permissao para criar avaliacoes.')
        return redirect('listar_avaliacoes_desempenho')

    initial = {}
    if request.method == 'GET':
        avaliado_id = request.GET.get('avaliado')
        if avaliado_id:
            try:
                avaliado_id = int(avaliado_id)
            except (TypeError, ValueError):
                avaliado_id = None
            if avaliado_id and usuarios_avaliaveis_para(request.user).filter(pk=avaliado_id).exists():
                initial['avaliado'] = avaliado_id

        for campo in ['ano', 'ciclo']:
            valor = request.GET.get(campo)
            if valor:
                initial[campo] = valor

    if request.method == 'POST':
        form = AvaliacaoDesempenhoForm(request.POST, usuario_logado=request.user)
        notas_form = NotasCompetenciasDesempenhoForm(request.POST)

        if form.is_valid() and notas_form.is_valid():
            with transaction.atomic():
                avaliacao = form.save(commit=False)
                avaliacao.avaliada_por = request.user
                _preencher_ciclo_avaliacao(avaliacao)
                preencher_snapshot_avaliacao(avaliacao)
                avaliacao.atualizar_status_ciencia()
                avaliacao.save()
                _salvar_notas_desempenho(avaliacao, notas_form.notas_limpas())

            messages.success(request, 'Avaliacao de desempenho cadastrada com sucesso.')
            return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)
    else:
        form = AvaliacaoDesempenhoForm(initial=initial, usuario_logado=request.user)
        notas_form = NotasCompetenciasDesempenhoForm()

    return render(request, 'rh/form_avaliacao_desempenho.html', {
        'form': form,
        'notas_form': notas_form,
        'titulo_pagina': 'Nova Avaliacao de Desempenho',
    })


@login_required(login_url='/login/')
def detalhe_avaliacao_desempenho(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if not pode_visualizar_resultado_avaliacao(request.user, avaliacao):
        messages.error(request, 'Você não possui permissão para visualizar esta avaliação.')
        return redirect('listar_avaliacoes_desempenho')

    return render(request, 'rh/detalhe_avaliacao_desempenho.html', {
        'avaliacao': avaliacao,
        'notas': avaliacao.notas.all(),
        'pode_editar': pode_editar_avaliacao(request.user, avaliacao),
    })


@login_required(login_url='/login/')
def editar_avaliacao_desempenho(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if not pode_editar_avaliacao(request.user, avaliacao):
        messages.error(request, 'Voce nao tem permissao para editar esta avaliacao.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    if request.method == 'POST':
        form = AvaliacaoDesempenhoForm(request.POST, instance=avaliacao, usuario_logado=request.user)
        notas_form = NotasCompetenciasDesempenhoForm(request.POST, avaliacao=avaliacao)

        if form.is_valid() and notas_form.is_valid():
            with transaction.atomic():
                avaliacao = form.save(commit=False)
                _preencher_ciclo_avaliacao(avaliacao)
                if not avaliacao.nome_avaliado:
                    preencher_snapshot_avaliacao(avaliacao)
                avaliacao.atualizar_status_ciencia()
                avaliacao.save()
                _salvar_notas_desempenho(avaliacao, notas_form.notas_limpas())

            messages.success(request, 'Avaliacao de desempenho atualizada com sucesso.')
            return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)
    else:
        form = AvaliacaoDesempenhoForm(instance=avaliacao, usuario_logado=request.user)
        notas_form = NotasCompetenciasDesempenhoForm(avaliacao=avaliacao)

    return render(request, 'rh/form_avaliacao_desempenho.html', {
        'form': form,
        'notas_form': notas_form,
        'avaliacao': avaliacao,
        'titulo_pagina': 'Editar Avaliacao de Desempenho',
    })


@login_required(login_url='/login/')
def dashboard_avaliacao_desempenho(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if not pode_visualizar_resultado_avaliacao(request.user, avaliacao):
        messages.error(request, 'Você não possui permissão para visualizar esta avaliação.')
        return redirect('listar_avaliacoes_desempenho')

    return render(request, 'rh/dashboard_avaliacao_desempenho.html', _dados_dashboard_avaliacao(avaliacao, request.user))


@login_required(login_url='/login/')
@require_POST
def dar_ciencia_gestor_avaliacao(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if not pode_dar_ciencia_gestor(request.user, avaliacao):
        messages.error(request, 'Voce nao tem permissao para registrar ciencia e concordancia como gestor nesta avaliacao.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    avaliacao.ciencia_gestor = True
    avaliacao.data_ciencia_gestor = timezone.now()
    avaliacao.usuario_ciencia_gestor = request.user
    avaliacao.atualizar_status_ciencia()
    avaliacao.save(update_fields=[
        'ciencia_gestor',
        'data_ciencia_gestor',
        'usuario_ciencia_gestor',
        'status',
        'atualizado_em',
    ])

    messages.success(request, 'Ciência e concordância do gestor registrada com sucesso.')
    return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)


@login_required(login_url='/login/')
@require_POST
def dar_ciencia_colaborador_avaliacao(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if avaliacao.avaliado_id != request.user.id:
        messages.error(request, 'Você só pode registrar ciência e concordância nas suas próprias avaliações.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    if avaliacao.ciencia_colaborador:
        messages.info(request, 'Sua ciência e concordância já foi registrada.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    if not avaliacao.ciencia_gestor:
        messages.warning(request, 'Você só poderá registrar ciência e concordância após a ciência e concordância do gestor.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    if not pode_dar_ciencia_colaborador(request.user, avaliacao):
        messages.error(request, 'Você só pode registrar ciência e concordância nas suas próprias avaliações.')
        return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)

    avaliacao.ciencia_colaborador = True
    avaliacao.data_ciencia_colaborador = timezone.now()
    avaliacao.usuario_ciencia_colaborador = request.user
    avaliacao.atualizar_status_ciencia()
    avaliacao.save(update_fields=[
        'ciencia_colaborador',
        'data_ciencia_colaborador',
        'usuario_ciencia_colaborador',
        'status',
        'atualizado_em',
    ])

    messages.success(request, 'Ciência e concordância do colaborador registrada com sucesso.')
    return redirect('dashboard_avaliacao_desempenho', pk=avaliacao.pk)


@login_required(login_url='/login/')
def exportar_pdf_avaliacao_desempenho(request, pk):
    avaliacao = get_object_or_404(avaliacoes_visiveis_para(request.user), pk=pk)
    if not pode_visualizar_resultado_avaliacao(request.user, avaliacao):
        messages.error(request, 'Você não possui permissão para visualizar esta avaliação.')
        return redirect('listar_avaliacoes_desempenho')

    dados = _dados_dashboard_avaliacao(avaliacao, request.user)
    notas = dados['notas']
    historico_avaliacoes = dados['historico_avaliacoes']
    historico_periodos = dados['historico_periodos']

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{_nome_arquivo_avaliacao(avaliacao)}"'

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TituloAvaliacao', parent=styles['Title'], alignment=TA_CENTER, fontSize=18, spaceAfter=12))
    styles.add(ParagraphStyle(name='SecaoAvaliacao', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#141C3C'), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name='TextoPequeno', parent=styles['BodyText'], fontSize=8, leading=10, alignment=TA_LEFT))
    normal = styles['BodyText']
    pequeno = styles['TextoPequeno']
    elementos = []

    logo_path = Path(settings.BASE_DIR) / 'static' / 'img' / 'logo.jpg'
    if logo_path.exists():
        elementos.append(Image(str(logo_path), width=3.0 * cm, height=1.6 * cm))
        elementos.append(Spacer(1, 0.15 * cm))

    elementos.append(Paragraph('AVALIACAO DE DESEMPENHO COLABORADOR - AD', styles['TituloAvaliacao']))
    resumo = [
        [_paragraph('<b>Colaborador</b>', normal), _paragraph(avaliacao.funcionario_nome, normal), _paragraph('<b>Cargo</b>', normal), _paragraph(avaliacao.funcionario_cargo, normal)],
        [_paragraph('<b>Setor</b>', normal), _paragraph(avaliacao.funcionario_setor, normal), _paragraph('<b>Data de admissao</b>', normal), _paragraph(avaliacao.funcionario_data_admissao.strftime('%d/%m/%Y') if avaliacao.funcionario_data_admissao else '-', normal)],
        [_paragraph('<b>Periodo atual</b>', normal), _paragraph(avaliacao.periodo_formatado, normal), _paragraph('<b>Data da avaliacao</b>', normal), _paragraph(timezone.localtime(avaliacao.data_avaliacao).strftime('%d/%m/%Y %H:%M') if avaliacao.data_avaliacao else '-', normal)],
        [_paragraph('<b>Avaliado por</b>', normal), _paragraph(avaliacao.avaliada_por.get_username() if avaliacao.avaliada_por else '-', normal), _paragraph('<b>Status</b>', normal), _paragraph(avaliacao.status_calculado_display, normal)],
    ]
    elementos.append(_tabela_pdf(resumo, [3.5 * cm, 5.0 * cm, 3.5 * cm, 5.0 * cm], header=False))
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph('Ciencia e Concordancia Digital', styles['SecaoAvaliacao']))
    elementos.append(_ciencia_pdf(avaliacao, normal))
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph('Criterios de Avaliacao', styles['SecaoAvaliacao']))
    criterios = [
        '10 - Acima de qualquer expectativa, um exemplo a ser seguido.',
        '9 - Excelente, sabe o que precisa para desempenhar seu papel.',
        '8 - Bom, desempenha corretamente suas atividades.',
        '7 - Desempenha corretamente, mas precisa de motivacao da equipe/gestor para cumprir seu papel.',
        '6 - Desempenha seu papel com algumas falhas e nao consegue motivar-se por conta propria.',
        '5 - Regular, precisa entender melhor seu papel, ter mais empenho e mudar comportamento.',
        '4 - Ruim, comportamento abaixo da expectativa, precisa de mudancas rapidas.',
        '3 - Ruim, comportamento bem abaixo da expectativa, nao esta correspondendo ao perfil desejado.',
        '2 - Pessimo, precisa de mudanca de comportamento urgente.',
        '1 - Pessimo, reavaliar.',
    ]
    elementos.append(_paragraph(' '.join(criterios), pequeno))
    elementos.append(Spacer(1, 0.3 * cm))

    elementos.append(Paragraph('Ficha comparativa por ciclo', styles['SecaoAvaliacao']))
    header = [_paragraph('Competencia', pequeno), _paragraph('Descricao', pequeno)] + [_paragraph(periodo.split(' - ')[0], pequeno) for periodo in historico_periodos]
    linhas = [header]
    for linha in dados['tabela_historico']:
        linhas.append([
            _paragraph(linha['competencia'].nome, pequeno),
            _paragraph(linha['competencia'].descricao, pequeno),
            *[_paragraph(valor, pequeno) for valor in linha['valores']],
        ])
    linhas.append([
        _paragraph('<b>Media</b>', pequeno),
        _paragraph('', pequeno),
        *[_paragraph(historico.media if historico.media is not None else '', pequeno) for historico in historico_avaliacoes],
    ])
    largura_periodo = max(1.1 * cm, (17.4 * cm - 8.8 * cm) / max(len(historico_periodos), 1))
    elementos.append(_tabela_pdf(linhas, [3.5 * cm, 5.3 * cm] + [largura_periodo] * len(historico_periodos)))
    elementos.append(Spacer(1, 0.3 * cm))

    comentarios = [[_paragraph('<b>Comentarios gerais</b>', normal), _paragraph(avaliacao.comentarios, normal)]]
    elementos.append(_tabela_pdf(comentarios, [4.2 * cm, 13.2 * cm], header=False))
    elementos.append(Spacer(1, 0.9 * cm))
    elementos.append(_assinaturas_pdf(avaliacao))

    elementos.append(PageBreak())
    elementos.append(Paragraph('AVALIACAO DE DESEMPENHO COLABORADOR', styles['TituloAvaliacao']))
    elementos.append(_tabela_pdf([
        [_paragraph('<b>Nome do colaborador</b>', normal), _paragraph(avaliacao.funcionario_nome, normal)],
        [_paragraph('<b>Periodo atual</b>', normal), _paragraph(avaliacao.periodo_formatado, normal)],
        [_paragraph('<b>Media atual</b>', normal), _paragraph(dados['media'], normal)],
        [_paragraph('<b>Classificacao</b>', normal), _paragraph(avaliacao.classificacao, normal)],
    ], [5.0 * cm, 12.0 * cm], header=False))
    elementos.append(Spacer(1, 0.35 * cm))
    elementos.append(Paragraph('Dashboard comparativo', styles['SecaoAvaliacao']))
    if notas:
        elementos.append(_grafico_barras_pdf(notas))
    if dados['medias_historico']:
        elementos.append(_grafico_medias_pdf(dados['medias_historico']))
    elementos.append(Spacer(1, 0.25 * cm))
    elementos.append(_tabela_pdf([
        [_paragraph('<b>Pontos fortes</b>', normal), _paragraph(', '.join(nota.competencia.nome for nota in dados['pontos_fortes']) or '-', normal)],
        [_paragraph('<b>Pontos de atencao</b>', normal), _paragraph(', '.join(nota.competencia.nome for nota in dados['pontos_atencao']) or '-', normal)],
        [_paragraph('<b>Abaixo da media</b>', normal), _paragraph(', '.join(nota.competencia.nome for nota in dados['competencias_abaixo_media']) or '-', normal)],
        [_paragraph('<b>Observacoes</b>', normal), _paragraph(avaliacao.comentarios, normal)],
    ], [4.5 * cm, 12.5 * cm], header=False))
    elementos.append(Spacer(1, 0.9 * cm))
    elementos.append(_assinaturas_pdf(avaliacao))

    doc.build(elementos)
    return response


@login_required(login_url='/login/')
def dashboard_geral_avaliacoes_desempenho(request):
    if not pode_criar_avaliacao(request.user):
        messages.error(request, 'Voce nao possui permissao para acessar o dashboard geral de avaliacoes.')
        return redirect('listar_avaliacoes_desempenho')

    avaliacoes = _aplicar_filtros_avaliacoes_desempenho(
        avaliacoes_visiveis_para(request.user).order_by('-data_avaliacao'),
        request.GET,
    )

    avaliacoes_lista = list(avaliacoes)
    medias = [(avaliacao, avaliacao.media) for avaliacao in avaliacoes_lista if avaliacao.media is not None]
    media_geral = round(sum(media for _, media in medias) / len(medias), 2) if medias else None

    ranking_maiores = sorted(medias, key=lambda item: item[1], reverse=True)[:10]
    ranking_menores = sorted(medias, key=lambda item: item[1])[:10]

    media_por_competencia = [
        {
            'competencia__nome': item['competencia__nome'],
            'competencia__ordem': item['competencia__ordem'],
            'media': round(float(item['media']), 2) if item['media'] is not None else None,
        }
        for item in NotaCompetenciaDesempenho.objects.filter(avaliacao__in=avaliacoes_lista)
        .values('competencia__nome', 'competencia__ordem')
        .annotate(media=Avg('nota'))
        .order_by('competencia__ordem', 'competencia__nome')
    ]

    media_por_setor = [
        {
            'setor': item['avaliacao__setor_avaliado'] or 'Sem setor',
            'media': round(float(item['media']), 2) if item['media'] is not None else None,
        }
        for item in NotaCompetenciaDesempenho.objects.filter(avaliacao__in=avaliacoes_lista)
        .values('avaliacao__setor_avaliado')
        .annotate(media=Avg('nota'))
        .order_by('avaliacao__setor_avaliado')
    ]

    qtd_por_ciclo = [
        {
            'ano': str(int(item['ano'])) if item['ano'] is not None else '',
            'ciclo': item['ciclo'],
            'total': item['total'],
        }
        for item in avaliacoes.values('ano', 'ciclo').annotate(total=Count('id')).order_by('ano', 'ciclo')
    ]
    qtd_por_status_contador = Counter(avaliacao.status_calculado for avaliacao in avaliacoes_lista)
    qtd_por_status = [
        {
            'status': AvaliacaoDesempenho.STATUS(status).label,
            'total': total,
        }
        for status, total in sorted(qtd_por_status_contador.items())
    ]

    evolucao = []
    for avaliacao, media in sorted(medias, key=lambda item: (item[0].funcionario_nome, item[0].ano, item[0].ciclo)):
        evolucao.append({
            'label': f'{avaliacao.funcionario_nome} - {avaliacao.ano_formatado}{avaliacao.ciclo}',
            'media': float(media),
        })

    context = {
        'avaliacoes': avaliacoes_lista,
        'funcionarios': _funcionarios_avaliacao_queryset(request.user),
        'setores': _opcoes_setores_para_template(request.user),
        'anos': _anos_avaliacoes_desempenho(),
        'status_choices': _status_choices_avaliacao_interface(),
        'ciclo_choices': AvaliacaoDesempenho.CICLO.choices,
        'filtros': request.GET,
        'media_geral': media_geral,
        'media_por_competencia': media_por_competencia,
        'media_por_setor': media_por_setor,
        'qtd_por_ciclo': qtd_por_ciclo,
        'qtd_por_status': qtd_por_status,
        'ranking_maiores': ranking_maiores,
        'ranking_menores': ranking_menores,
        'evolucao': evolucao,
        'pode_criar_avaliacao': pode_criar_avaliacao(request.user),
    }
    context.update(_usuarios_sem_avaliacao_context(request))
    return render(request, 'rh/dashboard_geral_avaliacoes_desempenho.html', context)

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


