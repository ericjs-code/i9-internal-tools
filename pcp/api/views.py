from __future__ import annotations

from typing import Any

import django_filters
from django.db.models import QuerySet
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from pcp.api.filters import (
    AtivoFilter,
    DowntimeFilter,
    ExecucaoManutencaoFilter,
    MovimentacaoEstoqueFilter,
    PlanoManutencaoFilter,
    ProgramacaoManutencaoFilter,
)
from pcp.api.permissions import PcpModulePermission, PowerBIApiKeyPermission
from pcp.api.serializers import (
    AreaProducaoSerializer,
    AtivoCreateSerializer,
    AtivoSerializer,
    DowntimeCloseSerializer,
    DowntimeOpenSerializer,
    DowntimeSerializer,
    ExecucaoManutencaoCloseSerializer,
    ExecucaoManutencaoSerializer,
    ExecucaoManutencaoStartSerializer,
    PlanoManutencaoCreateSerializer,
    PlanoManutencaoSerializer,
    ProgramacaoManutencaoSerializer,
    RecalcularPreventivasSerializer,
)
from pcp.models import PcpDowntime, PcpExecucaoManutencao
from pcp.selectors import (
    areas,
    ativos,
    downtimes,
    execucoes_manutencao,
    movimentacoes_estoque,
    planos_manutencao,
    programacoes_manutencao,
)
from pcp.services import AtivoService, DowntimeService, PlanoManutencaoService, ProgramacaoManutencaoService
from pcp.services.exceptions import PcpConflictError, PcpValidationError


class PCPPagination(PageNumberPagination):
    page_size = 5000
    page_size_query_param = "page_size"
    max_page_size = 20000


class OperationalPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class MovimentacaoEstoqueAPIView(APIView):
    permission_classes = [PowerBIApiKeyPermission]
    pagination_class = PCPPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(
            request=request,
            queryset=movimentacoes_estoque(),
            filterset_class=MovimentacaoEstoqueFilter,
        )
        queryset = queryset.values(
            "filial",
            "produto_codigo",
            "data_movimentacao",
            "tipo_movimentacao",
            "origem_movimentacao",
            "quantidade",
            "documento",
            "cf_operacao",
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(page)


class AreaProducaoAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return _paginated_response(view=self, request=request, queryset=areas(), serializer_class=AreaProducaoSerializer)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = AreaProducaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            area = AtivoService.criar_area(**serializer.validated_data)
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(AreaProducaoSerializer(area).data, status=status.HTTP_201_CREATED)


class AtivoAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(request=request, queryset=ativos(), filterset_class=AtivoFilter)
        return _paginated_response(view=self, request=request, queryset=queryset, serializer_class=AtivoSerializer)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = AtivoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ativo = AtivoService.criar_ativo(**serializer.validated_data)
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(AtivoSerializer(ativo).data, status=status.HTTP_201_CREATED)


class PlanoManutencaoAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(
            request=request,
            queryset=planos_manutencao(),
            filterset_class=PlanoManutencaoFilter,
        )
        return _paginated_response(view=self, request=request, queryset=queryset, serializer_class=PlanoManutencaoSerializer)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PlanoManutencaoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plano = PlanoManutencaoService.criar_plano(**serializer.validated_data)
        except PcpValidationError as exc:
            return _domain_error_response(exc)
        return Response(PlanoManutencaoSerializer(plano).data, status=status.HTTP_201_CREATED)


class ProgramacaoManutencaoAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(
            request=request,
            queryset=programacoes_manutencao(),
            filterset_class=ProgramacaoManutencaoFilter,
        )
        return _paginated_response(
            view=self,
            request=request,
            queryset=queryset,
            serializer_class=ProgramacaoManutencaoSerializer,
        )


class RecalcularPreventivasAPIView(APIView):
    permission_classes = [PcpModulePermission]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = RecalcularPreventivasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = ProgramacaoManutencaoService.recalcular_preventivas(**serializer.validated_data)
        return Response({"criadas": resultado.criadas, "existentes": resultado.existentes})


class DowntimeAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(request=request, queryset=downtimes(), filterset_class=DowntimeFilter)
        return _paginated_response(view=self, request=request, queryset=queryset, serializer_class=DowntimeSerializer)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = DowntimeOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            downtime = DowntimeService.abrir_downtime(**serializer.validated_data, responsavel=request.user)
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(DowntimeSerializer(downtime).data, status=status.HTTP_201_CREATED)


class DowntimeCloseAPIView(APIView):
    permission_classes = [PcpModulePermission]

    def post(self, request: Request, downtime_id: int, *args: Any, **kwargs: Any) -> Response:
        serializer = DowntimeCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            downtime = PcpDowntime.objects.get(pk=downtime_id)
            downtime = DowntimeService.fechar_downtime(downtime=downtime, **serializer.validated_data)
        except PcpDowntime.DoesNotExist:
            return Response({"erro": "Downtime não encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(DowntimeSerializer(downtime).data)


class ExecucaoManutencaoAPIView(APIView):
    permission_classes = [PcpModulePermission]
    pagination_class = OperationalPagination

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = _validated_filter_queryset(
            request=request,
            queryset=execucoes_manutencao(),
            filterset_class=ExecucaoManutencaoFilter,
        )
        return _paginated_response(
            view=self,
            request=request,
            queryset=queryset,
            serializer_class=ExecucaoManutencaoSerializer,
        )

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ExecucaoManutencaoStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            execucao = ProgramacaoManutencaoService.iniciar_execucao(
                **serializer.validated_data,
                responsavel=request.user,
            )
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(ExecucaoManutencaoSerializer(execucao).data, status=status.HTTP_201_CREATED)


class ExecucaoManutencaoCloseAPIView(APIView):
    permission_classes = [PcpModulePermission]

    def post(self, request: Request, execucao_id: int, *args: Any, **kwargs: Any) -> Response:
        serializer = ExecucaoManutencaoCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            execucao = PcpExecucaoManutencao.objects.get(pk=execucao_id)
            execucao = ProgramacaoManutencaoService.concluir_execucao(
                execucao=execucao,
                concluido_por=request.user,
                **serializer.validated_data,
            )
        except PcpExecucaoManutencao.DoesNotExist:
            return Response({"erro": "Execução não encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except (PcpValidationError, PcpConflictError) as exc:
            return _domain_error_response(exc)
        return Response(ExecucaoManutencaoSerializer(execucao).data)


def _validated_filter_queryset(
    *,
    request: Request,
    queryset: QuerySet[Any],
    filterset_class: type[django_filters.FilterSet],
) -> QuerySet[Any]:
    filterset = filterset_class(data=request.query_params, queryset=queryset)
    if not filterset.is_valid():
        raise ValidationError(filterset.errors)
    return filterset.qs


def _paginated_response(
    *,
    view: APIView,
    request: Request,
    queryset: QuerySet[Any],
    serializer_class: type[serializers.Serializer],
) -> Response:
    paginator = view.pagination_class()
    page = paginator.paginate_queryset(queryset, request, view=view)
    serializer = serializer_class(page, many=True)
    return paginator.get_paginated_response(serializer.data)


def _domain_error_response(exc: PcpValidationError | PcpConflictError) -> Response:
    response_status = status.HTTP_409_CONFLICT if isinstance(exc, PcpConflictError) else status.HTTP_400_BAD_REQUEST
    return Response({"erro": str(exc)}, status=response_status)
