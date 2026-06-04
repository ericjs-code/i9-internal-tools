from __future__ import annotations

import math
from datetime import datetime

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from pcp.models import (
    OrigemApontamento,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    StatusAtivo,
    TipoDowntime,
)
from pcp.services.exceptions import PcpConflictError, PcpValidationError


class DowntimeService:
    @staticmethod
    def abrir_downtime(
        *,
        ativo_pcp: PcpAtivo,
        motivo: str,
        tipo: str = TipoDowntime.NAO_PLANEJADO,
        inicio: datetime | None = None,
        origem: str = OrigemApontamento.MANUAL,
        responsavel: AbstractBaseUser | None = None,
        observacao: str = "",
    ) -> PcpDowntime:
        inicio = inicio or timezone.now()
        motivo_normalizado = motivo.strip()
        if not motivo_normalizado:
            raise PcpValidationError("Motivo do downtime é obrigatório.")

        try:
            with transaction.atomic():
                ativo = PcpAtivo.objects.select_for_update().get(pk=ativo_pcp.pk)
                if PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                    raise PcpConflictError("Já existe downtime aberto para este ativo.")

                downtime = PcpDowntime.objects.create(
                    ativo_pcp=ativo,
                    tipo=tipo,
                    inicio=inicio,
                    motivo=motivo_normalizado,
                    origem=origem,
                    responsavel=responsavel,
                    observacao=observacao.strip(),
                )
                ativo.status = StatusAtivo.PARADO
                ativo.save(update_fields=["status", "updated_at"])
                return downtime
        except IntegrityError as exc:
            raise PcpConflictError("Já existe downtime aberto para este ativo.") from exc

    @staticmethod
    def fechar_downtime(
        *,
        downtime: PcpDowntime,
        fim: datetime | None = None,
        observacao: str | None = None,
    ) -> PcpDowntime:
        fim = fim or timezone.now()

        with transaction.atomic():
            downtime = PcpDowntime.objects.select_for_update().select_related("ativo_pcp").get(pk=downtime.pk)
            if downtime.fim:
                return downtime
            if fim <= downtime.inicio:
                raise PcpValidationError("O fim deve ser posterior ao início do downtime.")

            downtime.fim = fim
            downtime.duracao_minutos = DowntimeService.calcular_duracao_minutos(inicio=downtime.inicio, fim=fim)
            if observacao is not None:
                downtime.observacao = observacao.strip()
            downtime.save(update_fields=["fim", "duracao_minutos", "observacao", "updated_at"])

            ativo = PcpAtivo.objects.select_for_update().get(pk=downtime.ativo_pcp_id)
            possui_outra_parada = PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exclude(
                pk=downtime.pk
            ).exists()
            if not possui_outra_parada:
                em_manutencao = PcpExecucaoManutencao.objects.filter(
                    ativo_pcp=ativo,
                    data_fim__isnull=True,
                ).exists()
                ativo.status = StatusAtivo.MANUTENCAO if em_manutencao else StatusAtivo.OPERANDO
                ativo.save(update_fields=["status", "updated_at"])

        return downtime

    @staticmethod
    def calcular_duracao_minutos(*, inicio: datetime, fim: datetime) -> int:
        if fim <= inicio:
            raise PcpValidationError("O fim deve ser posterior ao início do downtime.")
        return max(1, math.ceil((fim - inicio).total_seconds() / 60))

    @staticmethod
    def downtimes_abertos() -> QuerySet[PcpDowntime]:
        return PcpDowntime.objects.select_related("ativo_pcp", "ativo_pcp__area").filter(fim__isnull=True)
