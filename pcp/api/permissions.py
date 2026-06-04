from __future__ import annotations

import logging
from secrets import compare_digest
from typing import Any

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request


logger = logging.getLogger(__name__)


class PcpModulePermission(BasePermission):
    message = "Usuário sem permissão para acessar o módulo PCP."
    grupos_autorizados = {"PCP", "TI", "Diretoria"}

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=self.grupos_autorizados).exists()


class PowerBIApiKeyPermission(BasePermission):
    message = "Acesso não autorizado. API Key inválida ou ausente."

    def has_permission(self, request: Request, view: Any) -> bool:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning("Tentativa de acesso à API do Power BI sem Authorization.")
            return False

        try:
            auth_type, api_key = auth_header.split()
        except ValueError:
            logger.warning("Tentativa de acesso à API do Power BI com Authorization mal formatado.")
            return False

        if auth_type.lower() != "api-key":
            logger.warning("Tentativa de acesso à API do Power BI com tipo de autenticação incorreto.")
            return False

        expected_key = settings.POWER_BI_API_KEY
        if not expected_key:
            logger.error("POWER_BI_API_KEY não está configurada.")
            return False
        return compare_digest(api_key, expected_key)
