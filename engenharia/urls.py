from django.urls import path
from . import views

urlpatterns = [
    # Views principais da página
    path('extrai-estrutura-simples/', views.extrai_estrutura_simples, name='extrai_estrutura_simples'),
    path('atualizar-banco-estrutura/', views.atualizar_banco_estrutura, name='atualizar_banco_estrutura'),
    path('exportar-excel/', views.exportar_estrutura_excel, name='exportar_estrutura_excel'),

    # API Endpoints para HTMX (Lazy Loading da árvore)
    path('api/conjuntos-pai/<str:codigo_vo>/', views.get_conjuntos_pai, name='api_get_conjuntos_pai'),
    path('api/componentes-filho/<str:codigo_vo>/<str:codigo_pai>/', views.get_componentes_filho, name='api_get_componentes_filho'),
]
