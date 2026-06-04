from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser

from pcp.models import PcpEventoAuditoriaManutencao, PcpExecucaoManutencao


class AuditoriaManutencaoService:
    @staticmethod
    def registrar(
        *,
        execucao: PcpExecucaoManutencao,
        tipo_evento: str,
        usuario: AbstractBaseUser | None = None,
        justificativa: str = "",
        dados: dict[str, Any] | None = None,
    ) -> PcpEventoAuditoriaManutencao:
        return PcpEventoAuditoriaManutencao.objects.create(
            execucao=execucao,
            tipo_evento=tipo_evento,
            usuario=usuario,
            justificativa=justificativa.strip(),
            dados=dados or {},
        )
