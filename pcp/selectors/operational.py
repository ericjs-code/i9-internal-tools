from __future__ import annotations

from django.db.models import QuerySet
from django.db.models import Prefetch

from pcp.models import (
    MovimentacaoEstoquePCP,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
)


def movimentacoes_estoque() -> QuerySet[MovimentacaoEstoquePCP]:
    return MovimentacaoEstoquePCP.objects.order_by("data_movimentacao", "filial", "produto_codigo")


def areas() -> QuerySet[PcpAreaProducao]:
    return PcpAreaProducao.objects.order_by("codigo")


def ativos() -> QuerySet[PcpAtivo]:
    return PcpAtivo.objects.select_related("area").order_by("codigo")


def ativo_detalhado(*, ativo_id: int) -> PcpAtivo:
    execucoes = PcpExecucaoManutencao.objects.select_related("responsavel", "concluido_por").order_by("-data_inicio")
    planos = PcpPlanoManutencao.objects.prefetch_related("programacoes").order_by("nome")
    return (
        PcpAtivo.objects.select_related("area")
        .prefetch_related(
            Prefetch("planos_manutencao", queryset=planos),
            Prefetch("execucoes_manutencao", queryset=execucoes),
        )
        .get(pk=ativo_id)
    )


def planos_manutencao() -> QuerySet[PcpPlanoManutencao]:
    return PcpPlanoManutencao.objects.select_related("ativo_pcp").order_by("ativo_pcp__codigo", "nome")


def programacoes_manutencao() -> QuerySet[PcpProgramacaoManutencao]:
    return PcpProgramacaoManutencao.objects.select_related("plano", "plano__ativo_pcp").order_by("data_prevista")


def downtimes() -> QuerySet[PcpDowntime]:
    return PcpDowntime.objects.select_related("ativo_pcp", "responsavel").order_by("-inicio")


def execucoes_manutencao() -> QuerySet[PcpExecucaoManutencao]:
    return PcpExecucaoManutencao.objects.select_related(
        "ativo_pcp",
        "programacao",
        "programacao__plano",
        "responsavel",
    ).order_by("-data_inicio")


def execucao_detalhada(*, execucao_id: int) -> PcpExecucaoManutencao:
    return (
        PcpExecucaoManutencao.objects.select_related(
            "ativo_pcp__area",
            "programacao__plano",
            "responsavel",
            "concluido_por",
        )
        .prefetch_related("evidencias", "eventos_auditoria__usuario")
        .get(pk=execucao_id)
    )
