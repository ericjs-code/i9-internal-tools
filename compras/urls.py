from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_compras, name='dashboard_compras'),
    path('operacional/', views.dashboard_operacional, name='dashboard_operacional'),
    path('atualizar-dados/', views.atualizar_dados_dw, name='atualizar_dados_dw'),
    path('atualizar-pms/', views.atualizar_dados_pms, name='atualizar_dados_pms'),

    path('avaliacoes/pendentes/', views.listar_pedidos_avaliacao, name='listar_pedidos_avaliacao'),
    path('avaliacoes/nova/<str:numero_pedido>/', views.nova_avaliacao_fornecedor, name='nova_avaliacao_fornecedor'),
    path('avaliacoes/dashboard/', views.dashboard_avaliacoes, name='dashboard_avaliacoes'),
    path('avaliacoes/dashboard/exportar/', views.exportar_ranking_csv, name='exportar_ranking_csv')
]
