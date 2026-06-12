from __future__ import annotations

import django_filters

from pcp.models import (
    MovimentacaoEstoquePCP,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
)


class MovimentacaoEstoqueFilter(django_filters.FilterSet):
    data_inicio = django_filters.DateFilter(field_name="data_movimentacao", lookup_expr="gte")
    data_fim = django_filters.DateFilter(field_name="data_movimentacao", lookup_expr="lte")
    produto_codigo = django_filters.CharFilter(lookup_expr="exact")
    filial = django_filters.CharFilter(lookup_expr="exact")

    class Meta:
        model = MovimentacaoEstoquePCP
        fields = ["data_inicio", "data_fim", "produto_codigo", "filial", "tipo_movimentacao", "origem_movimentacao"]


class AtivoFilter(django_filters.FilterSet):
    class Meta:
        model = PcpAtivo
        fields = ["area", "status", "criticidade"]


class PlanoManutencaoFilter(django_filters.FilterSet):
    class Meta:
        model = PcpPlanoManutencao
        fields = ["ativo_pcp", "tipo"]


class ProgramacaoManutencaoFilter(django_filters.FilterSet):
    data_inicio = django_filters.DateFilter(field_name="data_prevista", lookup_expr="gte")
    data_fim = django_filters.DateFilter(field_name="data_prevista", lookup_expr="lte")
    ativo_pcp = django_filters.NumberFilter(field_name="plano__ativo_pcp_id")

    class Meta:
        model = PcpProgramacaoManutencao
        fields = ["ativo_pcp", "plano", "status", "data_inicio", "data_fim"]


class DowntimeFilter(django_filters.FilterSet):
    aberto = django_filters.BooleanFilter(field_name="fim", lookup_expr="isnull")
    data_inicio = django_filters.IsoDateTimeFilter(field_name="inicio", lookup_expr="gte")
    data_fim = django_filters.IsoDateTimeFilter(field_name="inicio", lookup_expr="lte")

    class Meta:
        model = PcpDowntime
        fields = ["ativo_pcp", "categoria", "tipo", "aberto", "data_inicio", "data_fim"]


class ExecucaoManutencaoFilter(django_filters.FilterSet):
    aberta = django_filters.BooleanFilter(field_name="data_fim", lookup_expr="isnull")
    inicio_de = django_filters.IsoDateTimeFilter(field_name="data_inicio", lookup_expr="gte")
    inicio_ate = django_filters.IsoDateTimeFilter(field_name="data_inicio", lookup_expr="lte")

    class Meta:
        model = PcpExecucaoManutencao
        fields = ["ativo_pcp", "programacao", "tipo", "responsavel", "aberta", "inicio_de", "inicio_ate"]
