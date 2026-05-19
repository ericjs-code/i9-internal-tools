from django.db import transaction
from django.utils import timezone

from .models import Chamado, ChamadoImagem
from .tasks import task_notificar_chamado


FECHAMENTO_AUTOMATICO_DIAS = 3


def abrir_chamado(*, form, solicitante):
    arquivos = form.cleaned_data.get('imagens') or []
    if not isinstance(arquivos, (list, tuple)):
        arquivos = [arquivos]

    with transaction.atomic():
        chamado = form.save(commit=False)
        chamado.solicitante = solicitante
        chamado.full_clean()
        chamado.save()

        for arquivo in arquivos:
            ChamadoImagem.objects.create(chamado=chamado, imagem=arquivo)

        _agendar_notificacao(chamado.id, 'ABERTURA', countdown=5)

    return chamado


def assumir_chamado(*, chamado, tecnico):
    status_anterior = chamado.status
    chamado.tecnico = tecnico
    if chamado.status in ['NOVO', 'ATRIBUIDO']:
        chamado.status = 'EM_ATENDIMENTO'

    chamado.full_clean()
    chamado.save()
    _notificar_se_status_mudou(chamado.id, status_anterior, chamado.status)
    return chamado


def atualizar_atendimento(*, form):
    estado_anterior = Chamado.objects.only('status', 'tecnico_id').get(pk=form.instance.pk)
    chamado = form.save(commit=False)
    chamado.full_clean()
    chamado.save()
    _notificar_alteracoes_atendimento(
        chamado_id=chamado.id,
        status_anterior=estado_anterior.status,
        status_atual=chamado.status,
        tecnico_anterior_id=estado_anterior.tecnico_id,
        tecnico_atual_id=chamado.tecnico_id,
    )
    return chamado


def validar_resolucao(*, chamado):
    status_anterior = chamado.status
    chamado.validado_pelo_solicitante = True
    chamado.status = 'CONCLUIDO'
    chamado.full_clean()
    chamado.save()
    _notificar_se_status_mudou(chamado.id, status_anterior, chamado.status)
    return chamado


def recusar_resolucao(*, chamado):
    status_anterior = chamado.status
    chamado.status = 'EM_ATENDIMENTO'
    chamado.full_clean()
    chamado.save()
    _notificar_se_status_mudou(chamado.id, status_anterior, chamado.status)
    return chamado


def fechar_chamados_resolvidos_sem_feedback(*, referencia=None, dias_sem_feedback=FECHAMENTO_AUTOMATICO_DIAS):
    referencia = referencia or timezone.now()
    limite = referencia - timezone.timedelta(days=dias_sem_feedback)

    chamados_elegiveis = Chamado.objects.filter(
        status='RESOLVIDO',
        validado_pelo_solicitante=False,
        encerrado_automaticamente=False,
        data_resolucao__lte=limite,
    ).only('id', 'status', 'validado_pelo_solicitante', 'encerrado_automaticamente', 'solucao', 'data_resolucao')

    chamados_fechados = []
    with transaction.atomic():
        for chamado in chamados_elegiveis.select_for_update():
            chamado.status = 'CONCLUIDO'
            chamado.encerrado_automaticamente = True
            chamado.full_clean()
            chamado.save(update_fields=['status', 'encerrado_automaticamente', 'data_fechamento'])
            chamados_fechados.append(chamado.id)

    for chamado_id in chamados_fechados:
        _agendar_notificacao(chamado_id, 'CONCLUSAO_AUTOMATICA')

    return chamados_fechados


def _notificar_se_status_mudou(chamado_id, status_anterior, status_atual):
    if status_anterior == status_atual:
        return

    tipo = 'CONCLUSAO' if status_atual == 'CONCLUIDO' else status_atual
    _agendar_notificacao(chamado_id, tipo)


def _notificar_alteracoes_atendimento(*, chamado_id, status_anterior, status_atual, tecnico_anterior_id, tecnico_atual_id):
    if status_anterior != status_atual:
        _notificar_se_status_mudou(chamado_id, status_anterior, status_atual)
        return

    if tecnico_anterior_id != tecnico_atual_id and tecnico_atual_id:
        _agendar_notificacao(chamado_id, 'ATRIBUIDO')


def _agendar_notificacao(chamado_id, tipo, countdown=None):
    def enqueue():
        if countdown:
            task_notificar_chamado.apply_async(args=[chamado_id, tipo], countdown=countdown)
        else:
            task_notificar_chamado.delay(chamado_id, tipo)

    transaction.on_commit(enqueue)
