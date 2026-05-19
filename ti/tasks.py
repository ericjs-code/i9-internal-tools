import json
import logging

import requests
from celery import shared_task
from django.apps import apps
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def task_notificar_chamado(self, chamado_id, tipo):
    Chamado = apps.get_model('ti', 'Chamado')

    try:
        chamado = Chamado.objects.select_related('solicitante', 'tecnico').get(id=chamado_id)
        enviar_notificacao_usuario(chamado, tipo)

        if tipo == 'ABERTURA':
            enviar_teams_ti(chamado)

        return f"Notificacoes processadas para chamado #{chamado.id} ({tipo})"
    except Exception as exc:
        logger.error("Erro ao processar notificacoes do chamado %s: %s", chamado_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def task_fechar_chamados_resolvidos_sem_feedback(self):
    try:
        from .services import fechar_chamados_resolvidos_sem_feedback

        chamados_fechados = fechar_chamados_resolvidos_sem_feedback()
        return f"{len(chamados_fechados)} chamados fechados automaticamente."
    except Exception as exc:
        logger.error("Erro ao fechar chamados sem feedback: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


def enviar_notificacao_usuario(chamado, tipo):
    webhook_user_url = getattr(settings, 'POWER_AUTOMATE_USER_WEBHOOK_URL', '')
    if not webhook_user_url:
        logger.error("POWER_AUTOMATE_USER_WEBHOOK_URL nao configurado.")
        return

    texto_msg, titulo_card = _mensagem_usuario(chamado, tipo)
    payload = {
        "Id": chamado.id,
        "solicitante": chamado.solicitante.get_full_name() or chamado.solicitante.username,
        "email": chamado.solicitante.email,
        "mensagem": texto_msg,
        "titulo": titulo_card,
    }

    response = requests.post(webhook_user_url, json=payload, timeout=15)
    response.raise_for_status()


def enviar_teams_ti(chamado):
    webhook_url = getattr(settings, 'TEAMS_TI_WEBHOOK_URL', '')
    if not webhook_url:
        logger.warning("TEAMS_TI_WEBHOOK_URL nao configurada.")
        return

    nome_solicitante = chamado.solicitante.get_full_name() or chamado.solicitante.username
    usuario_teams = getattr(chamado.solicitante, 'teams_username', None) or 'Nao cadastrado'

    card_data = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": f"Novo Chamado: {chamado.titulo}",
        "sections": [{
            "activityTitle": "Novo Chamado Aberto",
            "activitySubtitle": f"Solicitante: {nome_solicitante}",
            "activityText": f"User Teams: {usuario_teams}",
            "facts": [
                {"name": "ID:", "value": str(chamado.id)},
                {"name": "Setor:", "value": chamado.get_setor_display()},
                {"name": "Categoria:", "value": chamado.get_categoria_display()},
                {"name": "Prioridade:", "value": chamado.get_prioridade_display()},
                {"name": "Titulo:", "value": chamado.titulo},
            ],
            "markdown": True,
        }],
    }

    response = requests.post(
        webhook_url,
        data=json.dumps(card_data),
        headers={'Content-Type': 'application/json'},
        timeout=15,
    )
    response.raise_for_status()


def _mensagem_usuario(chamado, tipo):
    mensagens = {
        'ATRIBUIDO': (
            "Chamado Atribuido",
            f"Seu chamado foi encaminhado para analise por "
            f"{chamado.tecnico.get_full_name() if chamado.tecnico else 'um tecnico'}.",
        ),
        'EM_ANALISE': (
            "Em Analise Tecnica",
            "A equipe de TI esta analisando o seu problema neste momento.",
        ),
        'EM_ATENDIMENTO': (
            "Em Atendimento",
            "O tecnico iniciou a execucao/atendimento do seu chamado.",
        ),
        'AGUARDANDO_TERCEIRO': (
            "Aguardando Fornecedor/Peca",
            "O atendimento esta pausado aguardando uma peca ou suporte externo.",
        ),
        'AGUARDANDO_USUARIO': (
            "Aguardando Sua Resposta",
            "O tecnico precisa de mais informacoes para seguir. Verifique seu chamado.",
        ),
        'AGUARDANDO_APROVACAO': (
            "Aguardando Aprovacao",
            "O chamado depende da aprovacao do gestor ou area responsavel.",
        ),
        'CANCELADO': ("Chamado Cancelado", "A solicitacao foi cancelada."),
    }

    if tipo == 'ABERTURA':
        return "Chamado Aberto", f"Prioridade: {chamado.get_prioridade_display()} | Prazo: {chamado.calcular_sla()}"
    if tipo == 'RESOLVIDO':
        return (
            "Chamado Resolvido (Aguardando Voce)",
            f"A TI aplicou a seguinte solucao:\n{chamado.solucao}\n\nPor favor, valide no sistema.",
        )
    if tipo == 'CONCLUSAO':
        return "Chamado Concluido", f"Atendimento validado e encerrado.\nSolucao: {chamado.solucao}"
    if tipo == 'CONCLUSAO_AUTOMATICA':
        return (
            "Chamado Concluido Automaticamente",
            "O chamado foi encerrado automaticamente apos 3 dias sem retorno de validacao do solicitante."
            f"\nSolucao: {chamado.solucao}",
        )

    return mensagens.get(tipo, ("Atualizacao no Chamado", f"O status do seu chamado mudou para: {chamado.get_status_display()}"))
