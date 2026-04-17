import os
import pandas as pd
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction

from core.decorators import exige_permissao
from .models import EstruturaProduto
from .scripts.sync_estrutura import extrair_dados_engenharia, processar_estrutura, EXCEL_PATH


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def extrai_estrutura_simples(request):
    # Busca padrão
    estruturas = EstruturaProduto.objects.all().order_by('codigo_pai', 'nivel')

    # Captura o que o usuário digitou no Input de busca do HTML
    busca = request.GET.get('busca')

    # Se ele digitou algo, aplica o filtro no banco!
    if busca:
        estruturas = estruturas.filter(
            Q(codigo_pai__icontains=busca) |
            Q(codigo_componente__icontains=busca) |
            Q(descricao_pai__icontains=busca) |
            Q(descricao_componente__icontains=busca)
        )

    context = {
        'estruturas': estruturas
    }
    return render(request, 'engenharia/extrai_estrutura_simples.html', context)


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def exportar_estrutura_excel(request):
    """Gera um arquivo Excel fresh a partir dos dados do banco"""
    # Busca os dados
    estruturas = EstruturaProduto.objects.all().values()
    df = pd.DataFrame(list(estruturas))

    cols_datetime_com_tz = df.select_dtypes(include=['datetimetz']).columns

    for col in cols_datetime_com_tz:
        df[col] = df[col].dt.tz_localize(None)

    # 2. Configura a Resposta HTTP para Excel
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Relatorio_Engenharia.xlsx"'

    # 3. Salva o DataFrame direto na resposta
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    return response


@login_required(login_url='/login/')
@exige_permissao(['engenharia'])
def atualizar_banco_estrutura(request):
    """
    View acionada pelo botão 'Atualizar Relatório' no HTML dashboard.html.
    Executa o ETL e injeta os dados no banco.
    """
    try:
        extrair_dados_engenharia()
        processar_estrutura()

        # Lê o Excel gerado pelo ETL
        df = pd.read_excel(EXCEL_PATH)
        registros = []

        # Função auxiliar para tratar valores nulos do Pandas
        def limpa_str(val):
            return str(val).strip() if pd.notna(val) else ''

        def limpa_float(val):
            return float(val) if pd.notna(val) else 0.0

        # Varre o Excel linha por linha
        for index, row in df.iterrows():

            # Instanciando o objeto
            registros.append(EstruturaProduto(

                # --- OBRIGATÓRIOS ---
                codigo_pai=limpa_str(row.get('CODIGO_PAI')),
                descricao_pai=limpa_str(row.get('DESC_PAI')),
                nivel=limpa_str(row.get('G1_NIV')),
                codigo_componente=limpa_str(row.get('CODIGO')),
                descricao_componente=limpa_str(row.get('DESCRICAO')),

                tipo_pai=limpa_str(row.get('TIPO_PAI')),
                tipo_componente=limpa_str(row.get('TP')),

                quantidade_necessaria=limpa_float(row.get('QTDE.NECESSARIA')),
                quantidade=limpa_float(row.get('QTDE.NECESSARIA')),
                perda_percentual=limpa_float(row.get('G1_PERDA')),

                unidade_pai=limpa_str(row.get('UM_PAI','')),
                unidade_medida_filho=limpa_str(row.get('UM_COMPONENTE','')),
                tipo_quantidade=limpa_str(row.get('G1_FIXO')),

            ))

        # manda para o banco de dados
        with transaction.atomic():
            EstruturaProduto.objects.all().delete() # Limpa a tabela velha
            EstruturaProduto.objects.bulk_create(registros, batch_size=2000) # Injeta a nova

        messages.success(request, f"Estrutura atualizada com sucesso! {len(registros)} itens importados.")

    except Exception as e:
        messages.error(request, f"Erro ao atualizar a estrutura: {str(e)}")

    # Retorna para a página da engenharia
    return redirect('extrai_estrutura_simples')