from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Prefetch, QuerySet

from pcp.models import (
    MovimentacaoEstoquePCP,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpEvidenciaManutencao,
    PcpExecucaoManutencao,
    PcpEventoAuditoriaManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    StatusManutencao,
)


def movimentacoes_estoque() -> QuerySet[MovimentacaoEstoquePCP]:
    return MovimentacaoEstoquePCP.objects.order_by("data_movimentacao", "filial", "produto_codigo")


def areas() -> QuerySet[PcpAreaProducao]:
    return PcpAreaProducao.objects.order_by("codigo")


def ativos() -> QuerySet[PcpAtivo]:
    return PcpAtivo.objects.select_related("area").order_by("codigo")


def ativo_detalhado(*, ativo_id: int) -> PcpAtivo:
    programacoes = PcpProgramacaoManutencao.objects.order_by("data_prevista", "id")
    planos = PcpPlanoManutencao.objects.prefetch_related(
        Prefetch("programacoes", queryset=programacoes),
    ).order_by("nome", "id")
    execucoes = PcpExecucaoManutencao.objects.select_related(
        "programacao__plano",
        "responsavel",
        "concluido_por",
    ).order_by("-data_inicio", "-id")
    return (
        PcpAtivo.objects.prefetch_related(
            Prefetch("planos_manutencao", queryset=planos),
            Prefetch("execucoes_manutencao", queryset=execucoes),
        )
        .get(pk=ativo_id)
    )


def planos_manutencao() -> QuerySet[PcpPlanoManutencao]:
    return PcpPlanoManutencao.objects.select_related("ativo_pcp").order_by("ativo_pcp__codigo", "nome")


def programacoes_manutencao() -> QuerySet[PcpProgramacaoManutencao]:
    return PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp").order_by("data_prevista")


def agenda_manutencao(
    *,
    hoje: date,
    periodo: str = "90",
) -> QuerySet[PcpProgramacaoManutencao]:
    queryset = PcpProgramacaoManutencao.objects.select_related(
        "plano",
        "plano__ativo_pcp",
    ).filter(status=StatusManutencao.PLANEJADA)

    if periodo == "atrasadas":
        return queryset.filter(data_prevista__lt=hoje).order_by("data_prevista", "plano__ativo_pcp__codigo")
    if periodo == "hoje":
        return queryset.filter(data_prevista=hoje).order_by("plano__ativo_pcp__codigo")

    dias = int(periodo) if periodo in {"7", "15", "30", "90", "180", "365"} else 90
    limite = hoje + timedelta(days=dias)
    return queryset.filter(data_prevista__gte=hoje, data_prevista__lte=limite).order_by(
        "data_prevista",
        "plano__ativo_pcp__codigo",
    )


def downtimes() -> QuerySet[PcpDowntime]:
    return PcpDowntime.objects.select_related("ativo_pcp", "responsavel").order_by("-inicio")


def execucoes_manutencao() -> QuerySet[PcpExecucaoManutencao]:
    return PcpExecucaoManutencao.objects.select_related(
        "ativo_pcp",
        "programacao",
        "programacao__plano",
        "responsavel",
    ).order_by("-data_inicio")


def historico_manutencoes() -> QuerySet[PcpExecucaoManutencao]:
    evidencias = PcpEvidenciaManutencao.objects.order_by("created_at", "id")
    return (
        PcpExecucaoManutencao.objects.select_related(
            "ativo_pcp",
            "programacao__plano",
            "responsavel",
            "concluido_por",
        )
        .filter(data_fim__isnull=False)
        .prefetch_related(Prefetch("evidencias", queryset=evidencias))
        .order_by("-data_fim", "-id")
    )


def execucao_detalhada(*, execucao_id: int) -> PcpExecucaoManutencao:
    evidencias = PcpEvidenciaManutencao.objects.select_related("enviado_por").order_by(
        "finalidade", "created_at", "id"
    )
    eventos = PcpEventoAuditoriaManutencao.objects.select_related("usuario").order_by("-criado_em", "-id")
    return (
        PcpExecucaoManutencao.objects.select_related(
            "ativo_pcp",
            "programacao__plano",
            "responsavel",
            "concluido_por",
        )
        .prefetch_related(
            Prefetch("evidencias", queryset=evidencias),
            Prefetch("eventos_auditoria", queryset=eventos),
        )
        .get(pk=execucao_id)
    )
