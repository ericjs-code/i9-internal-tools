from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_qualidade, name='dashboard_qualidade'),
    path('api/rncs/', views.api_listar_rncs, name='api_listar_rncs'),
    path('api/rncs/<int:rnc_id>/atualizar/', views.api_atualizar_rnc, name='api_atualizar_rnc'),
    path('api/rncs/criar/', views.api_criar_rnc, name='api_criar_rnc'),
    path('api/rncs/<int:rnc_id>/editar-avancado/', views.api_editar_rnc_avancado, name='api_editar_rnc_avancado'),
    path('api/rncs/midia/<str:tipo>/<int:midia_id>/deletar/', views.api_deletar_midia_rnc, name='api_deletar_midia_rnc')
]