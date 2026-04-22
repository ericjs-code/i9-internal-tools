from django.urls import path
from . import views

urlpatterns = [
    path('vagas/', views.portal_vagas, name='portal_vagas'),
    path('vagas/<int:pk>/aplicar/', views.aplicar_vaga, name='aplicar_vaga'),
    path('painel/', views.triagem_rh, name='triagem_rh'),
    path('candidato/<int:pk>/', views.detalhe_candidato, name='detalhe_candidato'),
    path('gestao-vagas/', views.gestao_vagas, name='gestao_vagas'),
    path('gestao-vagas/nova/', views.form_vaga, name='nova_vaga'),
    path('gestao-vagas/<int:pk>/editar/', views.form_vaga, name='editar_vaga'),
    path('solicitar-vaga/', views.solicitar_abertura_vaga, name='solicitar_vaga'),
    path('solicitacoes/', views.listar_solicitacoes, name='listar_solicitacoes'),
    path('solicitacoes/<int:pk>/', views.detalhe_solicitacao, name='detalhe_solicitacao'),
    path('pesquisa-demissional/', views.listar_pesquisas, name='listar_pesquisas'),
    path('pesquisa-demissional/gerar/', views.gerar_pesquisa, name='gerar_pesquisa'),
    path('pesquisa-demissional/responder/<uuid:uuid_pesquisa>/', views.responder_pesquisa, name='responder_pesquisa'),
    path('pesquisas/', views.listar_pesquisas, name='listar_pesquisas'),
    path('dashboard/', views.dashboard_rh, name='dashboard_rh'),
    path('dashboard/importar/', views.importar_base_rh, name='importar_base_rh'),
    path('dashboard/importar-ponto/', views.importar_ponto_rh, name='importar_ponto_rh')
]