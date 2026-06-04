from __future__ import annotations

import logging
from datetime import date, timedelta
from hashlib import sha256
from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from pcp.models import (
    MARCOS_ALERTA_PREVENTIVA,
    PcpAlertaEnviado,
    PcpDowntime,
    PcpParametroAlerta,
    PcpProgramacaoAlertaManutencao,
    PcpProgramacaoManutencao,
    StatusAlerta,
    StatusManutencao,
    TipoAlerta,
)
from pcp.services.downtime import DowntimeService


logger = logging.getLogger(__name__)


class AlertaManutencaoService:
    @staticmethod
    def sincronizar_programacao(
        *,
        programacao: PcpProgramacaoManutencao,
        referencia: date | None = None,
    ) -> int:
        referencia = referencia or timezone.localdate()
        destinatarios = AlertaManutencaoService._destinatarios_preventiva()
        if not destinatarios:
            logger.warning("PCP_MAINTENANCE_ALERT_RECIPIENTS não possui destinatários válidos.")
            return 0

        destinatarios_texto = ",".join(destinatarios)
        criados = 0
        with transaction.atomic():
            programacao = PcpProgramacaoManutencao.all_objects.select_for_update().get(pk=programacao.pk)
            agendamentos = PcpProgramacaoAlertaManutencao.all_objects.select_for_update().filter(
                programacao=programacao,
                ativo=True,
            )

            if not programacao.ativo or programacao.status != StatusManutencao.PLANEJADA:
                agendamentos.exclude(status=StatusAlerta.ENVIADO).update(
                    ativo=False,
                    status=StatusAlerta.CANCELADO,
                    updated_at=timezone.now(),
                )
                return 0

            datas_esperadas = {
                marco: programacao.data_prevista - timedelta(days=marco) for marco in MARCOS_ALERTA_PREVENTIVA
            }
            for agendamento in agendamentos:
                data_esperada = datas_esperadas.get(agendamento.dias_antecedencia)
                if (
                    data_esperada != agendamento.data_disparo
                    or agendamento.destinatarios != destinatarios_texto
                ):
                    agendamento.ativo = False
                    agendamento.status = StatusAlerta.CANCELADO
                    agendamento.save(update_fields=["ativo", "status", "updated_at"])

            for marco, data_disparo in datas_esperadas.items():
                if data_disparo < referencia:
                    continue
                _, criado = PcpProgramacaoAlertaManutencao.objects.get_or_create(
                    programacao=programacao,
                    dias_antecedencia=marco,
                    destinatarios=destinatarios_texto,
                    defaults={"data_disparo": data_disparo},
                )
                criados += int(criado)

        return criados

    @staticmethod
    def sincronizar_alertas_preventivos(*, referencia: date | None = None) -> int:
        referencia = referencia or timezone.localdate()
        total = 0
        programacoes = PcpProgramacaoManutencao.objects.filter(status=StatusManutencao.PLANEJADA)
        for programacao in programacoes.iterator(chunk_size=200):
            total += AlertaManutencaoService.sincronizar_programacao(
                programacao=programacao,
                referencia=referencia,
            )
        return total

    @staticmethod
    def enviar_alertas_preventivas(*, referencia: date | None = None) -> int:
        referencia = referencia or timezone.localdate()
        AlertaManutencaoService.sincronizar_alertas_preventivos(referencia=referencia)
        total_enviados = 0
        agendamentos = (
            PcpProgramacaoAlertaManutencao.objects.select_related("programacao__plano__ativo_pcp")
            .filter(
                data_disparo__lte=referencia,
                status__in=[StatusAlerta.PENDENTE, StatusAlerta.FALHA],
                programacao__status=StatusManutencao.PLANEJADA,
                programacao__ativo=True,
            )
            .order_by("data_disparo", "id")
        )
        falhas = 0
        for agendamento in agendamentos.iterator(chunk_size=200):
            try:
                total_enviados += int(AlertaManutencaoService._enviar_email_preventiva(agendamento=agendamento))
            except Exception:
                falhas += 1
                logger.exception("Falha ao enviar alerta preventivo PCP id=%s.", agendamento.pk)
        if falhas:
            raise RuntimeError(f"Falha no envio de {falhas} alerta(s) preventivo(s) PCP.")
        return total_enviados

    @staticmethod
    def enviar_alertas_downtime_aberto() -> int:
        total_enviados = 0
        referencia = timezone.localdate()

        for downtime in DowntimeService.downtimes_abertos().iterator(chunk_size=200):
            parametros = PcpParametroAlerta.objects.filter(alertar_downtime_aberto=True).filter(
                Q(ativo_pcp=downtime.ativo_pcp)
                | Q(area=downtime.ativo_pcp.area)
                | Q(ativo_pcp__isnull=True, area__isnull=True)
            )
            for parametro in parametros.iterator(chunk_size=200):
                total_enviados += int(
                    AlertaManutencaoService._enviar_email_downtime(
                        parametro=parametro,
                        downtime=downtime,
                        destinatarios=AlertaManutencaoService._parse_emails(parametro.emails_destino),
                        data_referencia=referencia,
                    )
                )

        return total_enviados

    @staticmethod
    def _destinatarios_preventiva() -> list[str]:
        return AlertaManutencaoService._parse_emails(",".join(settings.PCP_MAINTENANCE_ALERT_RECIPIENTS))

    @staticmethod
    def _parse_emails(emails_destino: str) -> list[str]:
        normalized = emails_destino.replace(";", ",").replace("\n", ",")
        destinatarios: list[str] = []
        for email in normalized.split(","):
            email = email.strip().lower()
            if not email:
                continue
            try:
                validate_email(email)
            except ValidationError:
                continue
            destinatarios.append(email)
        return sorted(set(destinatarios))

    @staticmethod
    def _enviar_email_preventiva(*, agendamento: PcpProgramacaoAlertaManutencao) -> bool:
        programacao = agendamento.programacao
        ativo = programacao.plano.ativo_pcp
        destinatarios = AlertaManutencaoService._parse_emails(agendamento.destinatarios)
        assunto = f"[PCP] Manutenção em {agendamento.dias_antecedencia} dias - {ativo.codigo}"
        mensagem = (
            "Existe uma manutenção preventiva programada.\n\n"
            f"Ativo: {ativo.codigo} - {ativo.nome}\n"
            f"Plano: {programacao.plano.nome}\n"
            f"Data prevista: {programacao.data_prevista:%d/%m/%Y}\n"
            f"Antecedência: {agendamento.dias_antecedencia} dias\n"
            f"Status: {programacao.get_status_display()}\n"
        )
        try:
            enviado = AlertaManutencaoService._enviar_email_idempotente(
                tipo_alerta=TipoAlerta.PREVENTIVA,
                parametro=None,
                programacao=programacao,
                programacao_alerta=agendamento,
                downtime=None,
                data_referencia=agendamento.data_disparo,
                destinatarios=destinatarios,
                assunto=assunto,
                mensagem=mensagem,
            )
        except Exception as exc:
            PcpProgramacaoAlertaManutencao.all_objects.filter(pk=agendamento.pk).update(
                status=StatusAlerta.FALHA,
                tentativas=agendamento.tentativas + 1,
                ultimo_erro=str(exc)[:2000],
                updated_at=timezone.now(),
            )
            raise

        if enviado:
            PcpProgramacaoAlertaManutencao.all_objects.filter(pk=agendamento.pk).update(
                status=StatusAlerta.ENVIADO,
                tentativas=agendamento.tentativas + 1,
                enviado_em=timezone.now(),
                ultimo_erro="",
                updated_at=timezone.now(),
            )
        elif PcpAlertaEnviado.objects.filter(
            programacao_alerta=agendamento,
            status=StatusAlerta.ENVIADO,
        ).exists():
            PcpProgramacaoAlertaManutencao.all_objects.filter(pk=agendamento.pk).update(
                status=StatusAlerta.ENVIADO,
                enviado_em=timezone.now(),
                ultimo_erro="",
                updated_at=timezone.now(),
            )
        return enviado

    @staticmethod
    def _enviar_email_downtime(
        *,
        parametro: PcpParametroAlerta,
        downtime: PcpDowntime,
        destinatarios: Iterable[str],
        data_referencia: date,
    ) -> bool:
        assunto = f"[PCP] Downtime aberto - {downtime.ativo_pcp.codigo}"
        mensagem = (
            "Existe um downtime aberto no PCP.\n\n"
            f"Ativo: {downtime.ativo_pcp.codigo} - {downtime.ativo_pcp.nome}\n"
            f"Início: {timezone.localtime(downtime.inicio):%d/%m/%Y %H:%M}\n"
            f"Motivo: {downtime.motivo}\n"
        )
        return AlertaManutencaoService._enviar_email_idempotente(
            tipo_alerta=TipoAlerta.DOWNTIME_ABERTO,
            parametro=parametro,
            programacao=None,
            programacao_alerta=None,
            downtime=downtime,
            data_referencia=data_referencia,
            destinatarios=destinatarios,
            assunto=assunto,
            mensagem=mensagem,
        )

    @staticmethod
    def _enviar_email_idempotente(
        *,
        tipo_alerta: str,
        parametro: PcpParametroAlerta | None,
        programacao: PcpProgramacaoManutencao | None,
        programacao_alerta: PcpProgramacaoAlertaManutencao | None,
        downtime: PcpDowntime | None,
        data_referencia: date,
        destinatarios: Iterable[str],
        assunto: str,
        mensagem: str,
    ) -> bool:
        destinatarios_normalizados = sorted(set(destinatarios))
        if not destinatarios_normalizados:
            return False

        chave = AlertaManutencaoService._gerar_chave_idempotencia(
            tipo_alerta=tipo_alerta,
            parametro_id=parametro.id if parametro else None,
            objeto_id=programacao_alerta.id if programacao_alerta else downtime.id if downtime else None,
            data_referencia=data_referencia,
            destinatarios=destinatarios_normalizados,
        )
        alerta = AlertaManutencaoService._reservar_envio(
            chave=chave,
            tipo_alerta=tipo_alerta,
            parametro=parametro,
            programacao=programacao,
            programacao_alerta=programacao_alerta,
            downtime=downtime,
            data_referencia=data_referencia,
            destinatarios=destinatarios_normalizados,
            assunto=assunto,
        )
        if alerta is None:
            return False

        try:
            send_mail(
                subject=assunto,
                message=mensagem,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=destinatarios_normalizados,
                fail_silently=False,
            )
        except Exception as exc:
            PcpAlertaEnviado.all_objects.filter(pk=alerta.pk).update(
                status=StatusAlerta.FALHA,
                ultimo_erro=str(exc)[:2000],
                updated_at=timezone.now(),
            )
            raise

        PcpAlertaEnviado.all_objects.filter(pk=alerta.pk).update(
            status=StatusAlerta.ENVIADO,
            enviado_em=timezone.now(),
            ultimo_erro="",
            updated_at=timezone.now(),
        )
        return True

    @staticmethod
    def _reservar_envio(
        *,
        chave: str,
        tipo_alerta: str,
        parametro: PcpParametroAlerta | None,
        programacao: PcpProgramacaoManutencao | None,
        programacao_alerta: PcpProgramacaoAlertaManutencao | None,
        downtime: PcpDowntime | None,
        data_referencia: date,
        destinatarios: list[str],
        assunto: str,
    ) -> PcpAlertaEnviado | None:
        limite_envio_presumido = timezone.now() - timedelta(minutes=30)
        with transaction.atomic():
            alerta, _ = PcpAlertaEnviado.all_objects.get_or_create(
                chave_idempotencia=chave,
                defaults={
                    "tipo_alerta": tipo_alerta,
                    "parametro": parametro,
                    "programacao": programacao,
                    "programacao_alerta": programacao_alerta,
                    "downtime": downtime,
                    "data_referencia": data_referencia,
                    "destinatarios": ",".join(destinatarios),
                    "assunto": assunto,
                },
            )
            alerta = PcpAlertaEnviado.all_objects.select_for_update().get(pk=alerta.pk)
            if alerta.status == StatusAlerta.ENVIADO:
                return None
            if alerta.status == StatusAlerta.ENVIANDO and alerta.updated_at >= limite_envio_presumido:
                return None

            alerta.ativo = True
            alerta.status = StatusAlerta.ENVIANDO
            alerta.tentativas += 1
            alerta.ultimo_erro = ""
            alerta.save(update_fields=["ativo", "status", "tentativas", "ultimo_erro", "updated_at"])
            return alerta

    @staticmethod
    def _gerar_chave_idempotencia(
        *,
        tipo_alerta: str,
        parametro_id: int | None,
        objeto_id: int | None,
        data_referencia: date,
        destinatarios: Iterable[str],
    ) -> str:
        payload = "|".join(
            [
                tipo_alerta,
                str(parametro_id or ""),
                str(objeto_id or ""),
                data_referencia.isoformat(),
                ",".join(destinatarios),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()
