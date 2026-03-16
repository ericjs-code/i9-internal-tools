import json
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, F, ExpressionWrapper, fields
from django.db.models.functions import TruncDay
from django.utils import timezone
from .forms import AtendimentoChamadoForm, ChamadoForm, UsuarioForm
from .models import Chamado, ChamadoImagem



@login_required(login_url='/login/')
def novo_chamado(request):
    if request.method == 'POST':
        form = ChamadoForm(request.POST, request.FILES)
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.solicitante = request.user
            chamado.save()

            arquivos = request.FILES.getlist('imagens')
            for f in arquivos:
                ChamadoImagem.objects.create(chamado=chamado, imagem=f)

            messages.success(request, 'Chamado aberto com sucesso! A equipe de TI já foi notificada.')
            return redirect('meus_chamados')
        else:
            messages.error(request, 'Erro ao abrir o chamado. Verifique os campos.')
    else:
        form = ChamadoForm()

    return render(request, 'ti/chamado_form.html', {'form': form})


@login_required(login_url='/login/')
def ti_admin(request):
    if not (request.user.is_superuser or getattr(request.user, 'is_ti', False) or getattr(request.user.is_diretoria, False)):
        messages.error(request, "Acesso restrito à equipe de Tecnologia.")
        return redirect('home')

    chamados = Chamado.objects.exclude(status__in=['CONCLUIDO', 'CANCELADO', 'RESOLVIDO']).order_by('-data_abertura', '-id')
    total_abertos = chamados.count()
    meus_atendimentos = chamados.filter(tecnico=request.user).count()
    aguardando_validacao = Chamado.objects.filter(status='RESOLVIDO').count()

    context = {
        'chamados': chamados,
        'total_abertos': total_abertos,
        'meus_atendimentos': meus_atendimentos,
        'aguardando_validacao': aguardando_validacao,
    }
    return render(request, 'ti/ti_admin.html', context)


@login_required(login_url='/login/')
def dashboard_ti(request):
    if not (request.user.is_superuser or getattr(request.user, 'is_ti', False)):
        messages.error(request, "Acesso restrito à equipe de Tecnologia.")
        return redirect('home')

    total_chamados = Chamado.objects.exclude(status='CANCELADO').count()
    chamados_abertos = Chamado.objects.filter(status__in=['NOVO', 'ATRIBUIDO', 'EM_ANALISE']).count()
    chamados_andamento = Chamado.objects.filter(status='EM_ATENDIMENTO').count()
    chamados_concluidos = Chamado.objects.filter(status__in=['RESOLVIDO', 'CONCLUIDO']).count()
    chamados_terceiros = Chamado.objects.filter(status__in=['AGUARDANDO_TERCEIRO', 'AGUARDANDO_APROVACAO', 'AGUARDANDO_USUARIO']).count()

    tempo_medio_resultado = Chamado.objects.filter(status__in=['RESOLVIDO', 'CONCLUIDO']).aggregate(
        media=Avg(ExpressionWrapper(F('data_fechamento') - F('data_abertura'), output_field=fields.DurationField()))
    )['media']

    if tempo_medio_resultado:
        total_seconds = int(tempo_medio_resultado.total_seconds())
        dias = total_seconds // 86400
        horas = (total_seconds % 86400) // 3600
        tempo_medio_str = f"{dias}d {horas}h"
    else:
        tempo_medio_str = "0h"

    filtro = request.GET.get('filtro', '30')
    data_inicio = None
    agora = timezone.now()
    if filtro == '7': data_inicio = agora - timedelta(days=7)
    elif filtro == '30': data_inicio = agora - timedelta(days=30)
    elif filtro == '90': data_inicio = agora - timedelta(days=90)

    abertos_query = Chamado.objects.annotate(dia=TruncDay('data_abertura'))
    fechados_query = Chamado.objects.filter(status__in=['RESOLVIDO', 'CONCLUIDO']).exclude(data_fechamento__isnull=True).annotate(dia=TruncDay('data_fechamento'))

    if data_inicio:
        abertos_query = abertos_query.filter(data_abertura__gte=data_inicio)
        fechados_query = fechados_query.filter(data_fechamento__gte=data_inicio)

    abertos_query = abertos_query.values('dia').annotate(total=Count('id')).order_by('dia')
    fechados_query = fechados_query.values('dia').annotate(total=Count('id')).order_by('dia')

    dict_abertos = {item['dia']: item['total'] for item in abertos_query if item['dia']}
    dict_fechados = {item['dia']: item['total'] for item in fechados_query if item['dia']}
    todas_datas = sorted(set(dict_abertos.keys()) | set(dict_fechados.keys()))

    dia_labels = [d.strftime('%d/%m') for d in todas_datas]
    dia_data_abertos = [dict_abertos.get(d, 0) for d in todas_datas]
    dia_data_fechados = [dict_fechados.get(d, 0) for d in todas_datas]

    por_setor = Chamado.objects.values('setor').annotate(total=Count('id')).order_by('-total')
    setor_labels = [dict(Chamado.SETORES).get(item['setor'], item['setor']) for item in por_setor]
    setor_data = [item['total'] for item in por_setor]

    por_categoria = Chamado.objects.values('categoria').annotate(total=Count('id')).order_by('-total')
    categoria_labels = [dict(Chamado.CATEGORIAS).get(item['categoria'], item['categoria']) for item in por_categoria]
    categoria_data = [item['total'] for item in por_categoria]

    context = {
        'total_chamados': total_chamados, 'abertos': chamados_abertos, 'andamento': chamados_andamento,
        'concluidos': chamados_concluidos, 'terceiros': chamados_terceiros, 'tempo_medio': tempo_medio_str,
        'filtro_ativo': filtro,
        'setor_labels': json.dumps(setor_labels), 'setor_data': json.dumps(setor_data),
        'categoria_labels': json.dumps(categoria_labels), 'categoria_data': json.dumps(categoria_data),
        'dia_labels': json.dumps(dia_labels), 'dia_data_abertos': json.dumps(dia_data_abertos), 'dia_data_fechados': json.dumps(dia_data_fechados),
    }
    return render(request, 'ti/dashboard.html', context)


@login_required(login_url='/login/')
def atender_chamado(request, pk):
    if not (request.user.is_superuser or getattr(request.user, 'is_ti', False)):
        messages.error(request, "Acesso restrito à equipe de Tecnologia.")
        return redirect('home')

    chamado = get_object_or_404(Chamado, pk=pk)

    if request.method == 'POST':
        if 'assumir_chamado' in request.POST:
            chamado.tecnico = request.user
            if chamado.status in ['NOVO', 'ATRIBUIDO']:
                chamado.status = 'EM_ATENDIMENTO'
            chamado.save()
            messages.success(request, f"Você assumiu o chamado #{chamado.id}!")
            return redirect('atender_chamado', pk=chamado.id)

        form = AtendimentoChamadoForm(request.POST, instance=chamado)
        if form.is_valid():
            form.save()
            messages.success(request, "Chamado atualizado com sucesso!")
            return redirect('atender_chamado', pk=chamado.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Erro no campo {field}: {error}")
    else:
        form = AtendimentoChamadoForm(instance=chamado)

    return render(request, 'ti/atender_chamado.html', {'chamado': chamado, 'form': form})


@login_required(login_url='/login/')
def meus_chamados(request):
    chamados = Chamado.objects.filter(solicitante=request.user).order_by('-data_abertura')
    return render(request, 'ti/meus_chamados.html', {'chamados': chamados})


@login_required(login_url='/login/')
def detalhe_meu_chamado(request, pk):
    chamado = get_object_or_404(Chamado, pk=pk, solicitante=request.user)

    if request.method == 'POST':
        if chamado.status == 'RESOLVIDO':
            if 'validar_concluir' in request.POST:
                chamado.validado_pelo_solicitante = True
                chamado.status = 'CONCLUIDO'
                chamado.save()
                messages.success(request, 'Chamado validado e encerrado com sucesso. Obrigado!')
                return redirect('meus_chamados')

            elif 'recusar_resolucao' in request.POST:
                chamado.status = 'EM_ATENDIMENTO'
                chamado.save()
                messages.warning(request, 'O chamado foi devolvido para a equipe de TI continuar o atendimento.')
                return redirect('meus_chamados')

        else:
            messages.error(request, 'Este chamado não está aguardando validação.')

    return render(request, 'ti/meu_chamado_detalhe.html', {'chamado': chamado})


User = get_user_model()

@login_required(login_url='/login/')
def gestao_usuarios(request):
    """ Lista todos os usuários do ERP. Apenas TI e Diretoria acessam. """
    if not (request.user.is_superuser or getattr(request.user, 'is_ti', False) or getattr(request.user, 'is_diretoria', False)):
        messages.error(request, "Acesso restrito à TI.")
        return redirect('home')

    usuarios = User.objects.all().order_by('-is_active', 'username')
    return render(request, 'ti/gestao_usuarios.html', {'usuarios': usuarios})


@login_required(login_url='/login/')
def form_usuario(request, pk=None):
    if not (request.user.is_superuser or getattr(request.user, 'is_ti', False)):
        messages.error(request, "Acesso restrito à TI.")
        return redirect('home')

    if pk:
        usuario = get_object_or_404(User, pk=pk)
        titulo = "Editar Usuário"
    else:
        usuario = None
        titulo = "Novo Usuário"

    if request.method == 'POST':
        form = UsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            if not usuario and not form.cleaned_data.get('password'):
                messages.error(request, "Para novos usuários, a senha é obrigatória.")
            else:
                form.save()
                messages.success(request, f"Usuário {'atualizado' if usuario else 'criado'} com sucesso!")
                return redirect('gestao_usuarios')
    else:
        form = UsuarioForm(instance=usuario)

    return render(request, 'ti/form_usuario.html', {'form': form, 'titulo': titulo, 'usuario': usuario})