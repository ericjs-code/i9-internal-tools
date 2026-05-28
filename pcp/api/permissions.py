from rest_framework.permissions import BasePermission
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class PowerBIApiKeyPermission(BasePermission):
    """
    Permissão customizada para validar a API Key enviada pelo Power BI
    no header 'Authorization'.
    """
    message = 'Acesso não autorizado. API Key inválida ou ausente.'

    def has_permission(self, request, view):
        # O header deve ser 'Authorization: Api-Key <SUA_CHAVE>'
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            logger.warning("Tentativa de acesso à API do Power BI sem header 'Authorization'.")
            return False

        try:
            auth_type, api_key = auth_header.split()
        except ValueError:
            logger.warning(f"Tentativa de acesso à API do Power BI com header 'Authorization' mal formatado: {auth_header}")
            return False

        if auth_type.lower() != 'api-key':
            logger.warning(f"Tentativa de acesso à API do Power BI com tipo de autenticação incorreto: '{auth_type}'.")
            return False

        # Compara a chave enviada com a chave definida nas configurações do Django
        # Usar uma comparação segura para evitar ataques de timing
        expected_key = getattr(settings, 'POWER_BI_API_KEY', None)
        if not expected_key:
            logger.error("A variável de ambiente POWER_BI_API_KEY não está configurada no settings.py.")
            return False
            
        is_authorized = api_key == expected_key
        
        if not is_authorized:
            logger.warning(f"Tentativa de acesso à API do Power BI com API Key inválida: '{api_key[:10]}...'")

        return is_authorized
