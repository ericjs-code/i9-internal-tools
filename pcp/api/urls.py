from django.urls import path
from .views import MovimentacaoEstoqueAPIView

app_name = 'pcp_api'

urlpatterns = [
    path('powerbi/movimentacoes/', MovimentacaoEstoqueAPIView.as_view(), name='movimentacoes-powerbi'),
]
