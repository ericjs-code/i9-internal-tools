from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .permissions import PowerBIApiKeyPermission
from pcp.models import MovimentacaoEstoquePCP
import datetime

class PCPPagination(PageNumberPagination):
    page_size = 5000  # Tamanho generoso para ingestão eficiente do Power BI
    page_size_query_param = 'page_size'
    max_page_size = 20000

class MovimentacaoEstoqueAPIView(APIView):
    """
    Endpoint de alta performance para o Power BI extrair o histórico
    de movimentações de estoque do PCP.
    Protegido por API Key no header 'Authorization: Api-Key <token>'.
    """
    permission_classes = [PowerBIApiKeyPermission]
    pagination_class = PCPPagination

    def get(self, request, *args, **kwargs):
        queryset = MovimentacaoEstoquePCP.objects.all().order_by('data_movimentacao', 'produto_codigo')

        # Filtro opcional por data de início (recomendado para cargas incrementais no Power BI)
        data_inicio = request.query_params.get('data_inicio')
        if data_inicio:
            try:
                # Valida o formato ISO
                datetime.datetime.strptime(data_inicio, '%Y-%m-%d')
                queryset = queryset.filter(data_movimentacao__gte=data_inicio)
            except ValueError:
                return Response({"erro": "Formato de data_inicio inválido. Use AAAA-MM-DD."}, status=400)

        # Filtro opcional por código do produto
        produto = request.query_params.get('produto_codigo')
        if produto:
            queryset = queryset.filter(produto_codigo=produto)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        # Otimização Crítica: O uso de .values() evita que o Django ORM instancie
        # objetos complexos na memória para cada linha retornada. Ele retorna dicionários simples.
        data = list(page.values(
            'produto_codigo',
            'data_movimentacao',
            'tipo_movimentacao',
            'origem_movimentacao',
            'quantidade',
            'documento',
            'cf_operacao'
        ))

        return paginator.get_paginated_response(data)
