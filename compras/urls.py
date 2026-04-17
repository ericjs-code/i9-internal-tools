from django.urls import path
from . import views


urlpatterns = [
    path('dashboard/', views.dashboard_compras, name='dashboard_compras'),
    path('operacional/', views.dashboard_operacional, name='dashboard_operacional'),
    path('atualizar-dados/', views.atualizar_dados_dw, name='atualizar_dados_dw')
]