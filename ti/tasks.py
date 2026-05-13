import requests
import json
import logging
from celery import shared_task
from django.conf import settings
from django.apps import apps

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def task_notificar_chamado(self, chamado_id, tipo):
    """
    Task centralizada para notificações.
    Gerencia Webhooks do Teams (TI) e Power Automate (Usuário).
    """
    Chamado = apps.get_model('ti', 'Chamado')

    try:
        # Busca o chamado com select_related para performance
        chamado = Chamado.objects.select_related('solicitante', 'tecnico').get(id=chamado_id)

        # 1. NOTIFICAÇÃO PARA O USUÁRIO (Power Automate)
        enviar_notificacao_usuario(chamado, tipo)

        # 2. NOTIFICAÇÃO PARA A EQUIPE DE TI (Teams) - Apenas na abertura
        if tipo == 'ABERTURA':
            enviar_teams_ti(chamado)

        return f"Sucesso: Notificações enviadas para chamado #{chamado.id} (Tipo: {tipo})"

    except Exception as exc:
        logger.error(f"Erro ao processar notificações do chamado {chamado_id}: {exc}")
        # Tenta novamente em caso de erro de rede/timeout
        raise self.retry(exc=exc)


def enviar_notificacao_usuario(chamado, tipo):
    """Encapsula a lógica de mensagem para o solicitante"""
    webhook_user_url = "https://default367afcf4ee4944dfb034fc7437ee90.47.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/16a5c86eb81f49389610d053e5fa42c6/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=p1ycoRGzyZY5w_RGL-sGsuYAiLatbUw1Nb2KnCae0jo"

    texto_msg = ""
    titulo_card = ""

    # Mapeamento de mensagens baseado no tipo (mantendo sua lógica original)
    if tipo == 'ABERTURA':
        sla = chamado.calcular_sla()
        titulo_card = "Chamado Aberto"
        texto_msg = f"Prioridade: {chamado.get_prioridade_display()} | Prazo: {sla}"
    elif tipo == 'RESOLVIDO':
        titulo_card = "Chamado Resolvido (Aguardando Você)"
        texto_msg = f"A TI aplicou a seguinte solução:\n{chamado.solucao}\n\nPor favor, valide no sistema."
    elif tipo == 'CONCLUSAO':
        titulo_card = "Chamado Concluído"
        texto_msg = f"Atendimento validado e encerrado.\nSolução: {chamado.solucao}"
    else:
        titulo_card = "Atualização no Chamado"
        texto_msg = f"O status do seu chamado mudou para: {chamado.get_status_display()}"

    payload = {
        "Id": chamado.id,
        "solicitante": chamado.solicitante.get_full_name() or chamado.solicitante.username,
        "email": chamado.solicitante.email,
        "mensagem": texto_msg,
        "titulo": titulo_card
    }

    response = requests.post(webhook_user_url, json=payload, timeout=15)
    response.raise_for_status()


def enviar_teams_ti(chamado):
    """Encapsula o envio do MessageCard para o canal da TI"""
    # Usando a URL do settings por segurança
    webhook_url = settings.TEAMS_WEBHOOK_URL
    if not webhook_url:
        logger.warning("TEAMS_WEBHOOK_URL não configurada no .env")
        return

    nome_solicitante = chamado.solicitante.get_full_name() or chamado.solicitante.username
    # Fallback caso o campo teams_username não exista no CustomUser
    usuario_teams = getattr(chamado.solicitante, 'teams_username', 'Não cadastrado')

    card_data = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": f"Novo Chamado: {chamado.titulo}",
        "sections": [{
            "activityTitle": "🚨 Novo Chamado Aberto",
            "activitySubtitle": f"Solicitante: {nome_solicitante}",
            "activityText": f"User Teams: {usuario_teams}",
            "facts": [
                {"name": "ID:", "value": str(chamado.id)},
                {"name": "Setor:", "value": chamado.get_setor_display()},
                {"name": "Categoria:", "value": chamado.get_categoria_display()},
                {"name": "Prioridade:", "value": chamado.get_prioridade_display()},
                {"name": "Título:", "value": chamado.titulo}
            ],
            "markdown": True
        }]
    }

    response = requests.post(
        webhook_url,
        data=json.dumps(card_data),
        headers={'Content-Type': 'application/json'},
        timeout=15
    )
    response.raise_for_status()