from django.db.models import Avg
from compras.models import AvaliacaoFornecedor
import statistics


class ComprasBusinessService:
    @staticmethod
    def processar_ranking_fornecedores():
        """
        Calcula o ranking de fornecedores.
        Futuramente, substituiremos este loop manual por uma única Query do Django ORM.
        """
        avaliacoes = AvaliacaoFornecedor.objects.prefetch_related('respostas').all()
        fornecedores_data = {}

        for aval in avaliacoes:
            fornecedor = aval.nome_fornecedor
            if fornecedor not in fornecedores_data:
                fornecedores_data[fornecedor] = {'notas': [], 'qtd': 0}

            fornecedores_data[fornecedor]['qtd'] += 1
            notas = [resp.nota for resp in aval.respostas.all()]
            if notas:
                fornecedores_data[fornecedor]['notas'].append(sum(notas) / len(notas))

        ranking = []
        for nome, data in fornecedores_data.items():
            mediana = statistics.median(data['notas']) if data['notas'] else 0
            ranking.append({
                'fornecedor': nome,
                'mediana': mediana,
                'qtd_avaliacoes': data['qtd'],
                'risco': mediana < 8.0
            })

        return sorted(ranking, key=lambda x: (x['mediana'], -x['qtd_avaliacoes']))