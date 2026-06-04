from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from pcp.models import (
    OrigemApontamento,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    StatusManutencao,
    StatusAtivo,
    TipoManutencao,
    TipoEventoAuditoria,
)
from pcp.services.audit import AuditoriaManutencaoService
from pcp.services.exceptions import PcpConflictError, PcpValidationError


@dataclass(frozen=True)
class ProgramacaoResultado:
    programacao: PcpProgramacaoManutencao
    criada: bool


@dataclass(frozen=True)
class RecalculoResultado:
    criadas: int
    existentes: int


class PlanoManutencaoService:
    @staticmethod
    def criar_plano(
        *,
        ativo_pcp: PcpAtivo,
        nome: str,
        tipo: str = TipoManutencao.PREVENTIVA,
        descricao: str = "",
        intervalo_dias: int | None = None,
    ) -> PcpPlanoManutencao:
        PlanoManutencaoService._validar_intervalo(intervalo_dias=intervalo_dias)
        if not ativo_pcp.ativo:
            raise PcpValidationError("Não é permitido criar plano para ativo inativo.")

        with transaction.atomic():
            return PcpPlanoManutencao.objects.create(
                ativo_pcp=ativo_pcp,
                nome=nome.strip(),
                tipo=tipo,
                descricao=descricao.strip(),
                intervalo_dias=intervalo_dias,
            )

    @staticmethod
    def _validar_intervalo(*, intervalo_dias: int | None) -> None:
        if intervalo_dias is None or intervalo_dias <= 0:
            raise PcpValidationError("O intervalo de dias deve ser maior que zero.")


class ProgramacaoManutencaoService:
    STATUS_PENDENTES = (StatusManutencao.PLANEJADA, StatusManutencao.EM_EXECUCAO)

    @staticmethod
    def calcular_data_proxima_preventiva(
        *,
        plano: PcpPlanoManutencao,
        referencia: date | None = None,
    ) -> date:
        if plano.intervalo_dias is None or plano.intervalo_dias <= 0:
            raise PcpValidationError("Plano ativo exige intervalo de dias maior que zero.")

        base = ProgramacaoManutencaoService._data_base(plano=plano, referencia=referencia)
        return base + timedelta(days=plano.intervalo_dias)

    @staticmethod
    def gerar_proxima_preventiva(
        *,
        plano: PcpPlanoManutencao,
        referencia: date | None = None,
        origem: str = OrigemApontamento.SISTEMA,
    ) -> ProgramacaoResultado:
        with transaction.atomic():
            plano = PcpPlanoManutencao.objects.select_for_update().select_related("ativo_pcp").get(pk=plano.pk)
            if not plano.ativo or not plano.ativo_pcp.ativo:
                raise PcpValidationError("Plano e ativo devem estar ativos para gerar programação.")

            existente = ProgramacaoManutencaoService._programacoes_pendentes(plano=plano).first()
            if existente:
                return ProgramacaoResultado(programacao=existente, criada=False)

            data_prevista = ProgramacaoManutencaoService.calcular_data_proxima_preventiva(
                plano=plano,
                referencia=referencia,
            )
            programacao = PcpProgramacaoManutencao.objects.create(
                plano=plano,
                data_prevista=data_prevista,
                data_limite=data_prevista,
                status=StatusManutencao.PLANEJADA,
                origem=origem,
            )
            from pcp.services.alerts import AlertaManutencaoService

            AlertaManutencaoService.sincronizar_programacao(programacao=programacao, referencia=referencia)
            return ProgramacaoResultado(programacao=programacao, criada=True)

    @staticmethod
    def recalcular_preventivas(*, referencia: date | None = None) -> RecalculoResultado:
        planos = PcpPlanoManutencao.objects.select_related("ativo_pcp").filter(
            tipo=TipoManutencao.PREVENTIVA,
            intervalo_dias__isnull=False,
            ativo_pcp__ativo=True,
        )
        criadas = 0
        existentes = 0

        for plano in planos.iterator(chunk_size=500):
            resultado = ProgramacaoManutencaoService.gerar_proxima_preventiva(
                plano=plano,
                referencia=referencia,
                origem=OrigemApontamento.CELERY,
            )
            if resultado.criada:
                criadas += 1
            else:
                existentes += 1

        return RecalculoResultado(criadas=criadas, existentes=existentes)

    @staticmethod
    def concluir_execucao(
        *,
        execucao: PcpExecucaoManutencao,
        data_fim: datetime | None = None,
        concluido_por: AbstractBaseUser | None = None,
        diagnostico: str = "",
        servicos_executados: str = "",
        resultado: str = "",
        recomendacoes: str = "",
    ) -> PcpExecucaoManutencao:
        data_fim = data_fim or timezone.now()

        with transaction.atomic():
            execucao = (
                PcpExecucaoManutencao.objects.select_for_update(of=("self",))
                .select_related("programacao__plano", "ativo_pcp__area")
                .get(pk=execucao.pk)
            )
            if execucao.data_fim:
                raise PcpConflictError("Execução já foi concluída.")
            if data_fim <= execucao.data_inicio:
                raise PcpValidationError("A data de fim deve ser posterior à data de início.")

            execucao.data_fim = data_fim
            execucao.concluido_em = timezone.now()
            execucao.concluido_por = concluido_por
            execucao.diagnostico = diagnostico.strip()
            execucao.servicos_executados = servicos_executados.strip()
            execucao.resultado = resultado.strip()
            execucao.recomendacoes = recomendacoes.strip()
            execucao.snapshot_ativo_codigo = execucao.ativo_pcp.codigo
            execucao.snapshot_ativo_nome = execucao.ativo_pcp.nome
            execucao.snapshot_ativo_numero_serie = execucao.ativo_pcp.numero_serie
            execucao.snapshot_area_nome = execucao.ativo_pcp.area.nome
            if execucao.programacao_id:
                execucao.snapshot_plano_nome = execucao.programacao.plano.nome
                execucao.snapshot_plano_tipo = execucao.programacao.plano.tipo
            execucao.save(
                update_fields=[
                    "data_fim",
                    "concluido_em",
                    "concluido_por",
                    "diagnostico",
                    "servicos_executados",
                    "resultado",
                    "recomendacoes",
                    "snapshot_ativo_codigo",
                    "snapshot_ativo_nome",
                    "snapshot_ativo_numero_serie",
                    "snapshot_area_nome",
                    "snapshot_plano_nome",
                    "snapshot_plano_tipo",
                    "updated_at",
                ]
            )
            AuditoriaManutencaoService.registrar(
                execucao=execucao,
                tipo_evento=TipoEventoAuditoria.CONCLUIDA,
                usuario=concluido_por,
                dados={"data_fim": data_fim.isoformat()},
            )

            if execucao.programacao_id:
                execucao.programacao.status = StatusManutencao.CONCLUIDA
                execucao.programacao.save(update_fields=["status", "updated_at"])
                from pcp.services.alerts import AlertaManutencaoService

                AlertaManutencaoService.sincronizar_programacao(programacao=execucao.programacao)
                ProgramacaoManutencaoService.gerar_proxima_preventiva(
                    plano=execucao.programacao.plano,
                    referencia=data_fim.date(),
                    origem=OrigemApontamento.SISTEMA,
                )

            ativo = PcpAtivo.objects.select_for_update().get(pk=execucao.ativo_pcp_id)
            if not PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                ativo.status = StatusAtivo.OPERANDO
                ativo.save(update_fields=["status", "updated_at"])

        return execucao

    @staticmethod
    def iniciar_execucao(
        *,
        ativo_pcp: PcpAtivo,
        tipo: str,
        data_inicio: datetime | None = None,
        responsavel: AbstractBaseUser | None = None,
        programacao: PcpProgramacaoManutencao | None = None,
        observacao: str = "",
    ) -> PcpExecucaoManutencao:
        data_inicio = data_inicio or timezone.now()
        try:
            with transaction.atomic():
                ativo = PcpAtivo.objects.select_for_update().get(pk=ativo_pcp.pk)
                if PcpExecucaoManutencao.objects.filter(ativo_pcp=ativo, data_fim__isnull=True).exists():
                    raise PcpConflictError("Já existe uma execução de manutenção aberta para este ativo.")

                if programacao:
                    programacao = PcpProgramacaoManutencao.objects.select_for_update().select_related("plano").get(
                        pk=programacao.pk
                    )
                    if programacao.plano.ativo_pcp_id != ativo.pk:
                        raise PcpValidationError("A programação não pertence ao ativo informado.")
                    if programacao.plano.tipo != tipo:
                        raise PcpValidationError("O tipo da execução deve corresponder ao tipo do plano.")
                    if programacao.status != StatusManutencao.PLANEJADA:
                        raise PcpConflictError("Somente programações planejadas podem ser iniciadas.")
                    programacao.status = StatusManutencao.EM_EXECUCAO
                    programacao.save(update_fields=["status", "updated_at"])

                execucao = PcpExecucaoManutencao.objects.create(
                    programacao=programacao,
                    ativo_pcp=ativo,
                    tipo=tipo,
                    data_inicio=data_inicio,
                    responsavel=responsavel,
                    observacao=observacao.strip(),
                )
                AuditoriaManutencaoService.registrar(
                    execucao=execucao,
                    tipo_evento=TipoEventoAuditoria.INICIADA,
                    usuario=responsavel,
                    dados={"data_inicio": data_inicio.isoformat()},
                )
                if not PcpDowntime.objects.filter(ativo_pcp=ativo, fim__isnull=True).exists():
                    ativo.status = StatusAtivo.MANUTENCAO
                    ativo.save(update_fields=["status", "updated_at"])
                return execucao
        except IntegrityError as exc:
            raise PcpConflictError("Já existe uma execução de manutenção aberta para este ativo.") from exc

    @staticmethod
    def _programacoes_pendentes(*, plano: PcpPlanoManutencao) -> QuerySet[PcpProgramacaoManutencao]:
        return PcpProgramacaoManutencao.objects.filter(
            plano=plano,
            status__in=ProgramacaoManutencaoService.STATUS_PENDENTES,
        ).order_by("data_prevista", "id")

    @staticmethod
    def _data_base(*, plano: PcpPlanoManutencao, referencia: date | None) -> date:
        ultima_execucao = (
            PcpExecucaoManutencao.objects.filter(
                programacao__plano=plano,
                data_fim__isnull=False,
            )
            .order_by("-data_fim")
            .first()
        )
        if ultima_execucao and ultima_execucao.data_fim:
            return timezone.localtime(ultima_execucao.data_fim).date()
        return referencia or timezone.localdate()
