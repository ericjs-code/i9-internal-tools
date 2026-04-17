from django.urls import path
from . import views

urlpatterns = [
    path('extrai-estrutura-simples/', views.extrai_estrutura_simples, name='extrai_estrutura_simples'),
    path('atualizar-banco-estrutura/', views.atualizar_banco_estrutura, name='atualizar_banco_estrutura'),
    path('exportar-excel/', views.exportar_estrutura_excel, name='exportar_estrutura_excel')
]