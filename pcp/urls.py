from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/", views.dashboard_pcp, name="dashboard_pcp"),
    path("ativos/", views.listar_ativos, name="pcp_listar_ativos"),
    path("ativos/novo/", views.criar_ativo, name="pcp_criar_ativo"),
    path("ativos/<int:ativo_id>/", views.detalhar_ativo, name="pcp_detalhar_ativo"),
    path("ativos/<int:ativo_id>/editar/", views.editar_ativo, name="pcp_editar_ativo"),
    path("ativos/<int:ativo_id>/desativar/", views.desativar_ativo, name="pcp_desativar_ativo"),
    path("ativos/<int:ativo_id>/manutencoes/nova/", views.iniciar_manutencao, name="pcp_iniciar_manutencao"),
    path("manutencoes/<int:execucao_id>/", views.detalhar_execucao, name="pcp_detalhar_execucao"),
    path(
        "manutencoes/<int:execucao_id>/concluir/",
        views.concluir_manutencao,
        name="pcp_concluir_manutencao",
    ),
    path(
        "manutencoes/<int:execucao_id>/evidencias/",
        views.adicionar_evidencia,
        name="pcp_adicionar_evidencia",
    ),
    path("evidencias/<int:evidencia_id>/download/", views.baixar_evidencia, name="pcp_baixar_evidencia"),
]
