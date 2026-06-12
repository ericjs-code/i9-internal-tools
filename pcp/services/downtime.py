from __future__ import annotations

import math
from datetime import datetime

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from pcp.models import (
    CATEGORIA_POR_TIPO_DOWNTIME,
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
        tipo: str = TipoDowntime.MAQUINARIO_ESTRAGOU,
        inicio: datetime | None = None,
        origem: str = OrigemApontamento.MANUAL,
        responsavel: AbstractBaseUser | None = None,
        observacao: str = "",
    ) -> PcpDowntime:
        inicio = inicio or timezone.now()
        motivo_normalizado = motivo.strip()
        if not motivo_normalizado:
            raise PcpValidationError("Motivo do downtime é obrigatório.")
        categoria = DowntimeService.categoria_do_tipo(tipo=tipo)

        with transaction.atomic():
            ativo = PcpAtivo.objects.select_for_update().get(pk=ativo_pcp.pk)
            if PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                raise PcpConflictError("Já existe downtime aberto para este ativo.")

            try:
                with transaction.atomic():
                    downtime = PcpDowntime.objects.create(
                        ativo_pcp=ativo,
                        categoria=categoria,
                        tipo=tipo,
                        inicio=inicio,
                        motivo=motivo_normalizado,
                        origem=origem,
                        responsavel=responsavel,
                        observacao=observacao.strip(),
                    )
            except IntegrityError as exc:
                if PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                    raise PcpConflictError("Já existe downtime aberto para este ativo.") from exc
                raise PcpValidationError("Não foi possível registrar a parada com o tipo informado.") from exc

            ativo.status = StatusAtivo.PARADO
            ativo.save(update_fields=["status", "updated_at"])
            return downtime

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
    def categoria_do_tipo(*, tipo: str) -> str:
        categoria = CATEGORIA_POR_TIPO_DOWNTIME.get(tipo)
        if categoria is None or tipo not in TipoDowntime.values:
            raise PcpValidationError("Tipo de parada inválido.")
        return categoria

    @staticmethod
    def downtimes_abertos() -> QuerySet[PcpDowntime]:
        return PcpDowntime.objects.select_related("ativo_pcp").filter(fim__isnull=True)
