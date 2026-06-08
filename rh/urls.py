from django.urls import path
from . import views

urlpatterns = [
    path('vagas/', views.job_list, name='job_list'),
    path('vagas/<int:pk>/aplicar/', views.job_apply, name='job_apply'),
    path('painel/', views.candidate_screening, name='candidate_screening'),
    path('candidato/<int:pk>/', views.candidate_datail, name='candidate_datail'),
    path('gestao-vagas/', views.job_management, name='job_management'),
    path('gestao-vagas/nova/', views.job_form, name='nova_vaga'),
    path('gestao-vagas/<int:pk>/editar/', views.job_form, name='editar_vaga'),
    path('solicitar-vaga/', views.solicitar_abertura_vaga, name='solicitar_vaga'),
    path('solicitacoes/', views.listar_solicitacoes, name='listar_solicitacoes'),
    path('solicitacoes/<int:pk>/', views.detalhe_solicitacao, name='detalhe_solicitacao'),
    path('pesquisa-demissional/', views.listar_pesquisas, name='listar_pesquisas'),
    path('pesquisa-demissional/gerar/', views.gerar_pesquisa, name='gerar_pesquisa'),
    path('pesquisa-demissional/responder/<uuid:uuid_pesquisa>/', views.responder_pesquisa, name='responder_pesquisa'),
    path('formulario-admissional/', views.listar_formularios_admissionais, name='listar_formularios_admissionais'),
    path('formulario-admissional/gerar/', views.gerar_formulario_admissional, name='gerar_formulario_admissional'),
    path('formulario-admissional/<uuid:uuid_formulario>/', views.detalhe_formulario_admissional, name='detalhe_formulario_admissional'),
    path('formulario-admissional/responder/<uuid:uuid_formulario>/', views.responder_formulario_admissional, name='responder_formulario_admissional'),
    path('pesquisas/', views.listar_pesquisas, name='listar_pesquisas'),
    path('dashboard/', views.dashboard_rh, name='dashboard_rh'),
    path('dashboard/importar/', views.importar_base_rh, name='importar_base_rh'),
    path('dashboard/importar-ponto/', views.importar_ponto_rh, name='importar_ponto_rh')
]
