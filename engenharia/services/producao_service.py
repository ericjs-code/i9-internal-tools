import pandas as pd
from django.db.models import Q
from typing import List, Dict, Any

from engenharia.models import EstruturaProduto


class ProducaoQueryService:
    """
    Serviço responsável por encapsular as queries e transformações
    de dados do módulo de Engenharia para entrega às Views/APIs.
    """

    @classmethod
    def get_projetos_vo(cls, termo_busca: str = None) -> List[Dict[str, Any]]:
        """
        Retorna a lista de Projetos (VO) únicos de forma otimizada.
        """
        query = EstruturaProduto.objects.all()

        if termo_busca:
            # Filtra os VOs que correspondem diretamente à busca, ou cujos filhos/pais correspondem
            query = query.filter(
                Q(codigo_vo__icontains=termo_busca) |
                Q(descricao_vo__icontains=termo_busca) |
                Q(codigo_pai__icontains=termo_busca) |
                Q(descricao_pai__icontains=termo_busca) |
                Q(codigo_filho__icontains=termo_busca) |
                Q(descricao_filho__icontains=termo_busca)
            )

        # Usando values() e distinct() para otimizar a consulta
        # para trazer apenas os projetos únicos, sem carregar todos os filhos na memória.
        vo_queryset = query.values('codigo_vo', 'descricao_vo').distinct().order_by('codigo_vo')
        
        return list(vo_queryset)

    @classmethod
    def get_conjuntos_pai(cls, codigo_vo: str, termo_busca: str = None) -> List[Dict[str, Any]]:
        """
        Retorna a lista de Conjuntos (Pai) únicos para um Projeto (VO) específico.
        """
        query = EstruturaProduto.objects.filter(codigo_vo=codigo_vo)

        if termo_busca:
             query = query.filter(
                Q(codigo_pai__icontains=termo_busca) |
                Q(descricao_pai__icontains=termo_busca) |
                Q(codigo_filho__icontains=termo_busca) |
                Q(descricao_filho__icontains=termo_busca)
             )

        pai_queryset = query.values('codigo_pai', 'descricao_pai').distinct().order_by('codigo_pai')
        return list(pai_queryset)

    @classmethod
    def get_componentes_filho(cls, codigo_vo: str, codigo_pai: str, termo_busca: str = None) -> List[Dict[str, Any]]:
        """
        Retorna a lista de Componentes (Filhos) para um Conjunto (Pai) e Projeto (VO) específicos.
        """
        query = EstruturaProduto.objects.filter(codigo_vo=codigo_vo, codigo_pai=codigo_pai)

        if termo_busca:
            query = query.filter(
                Q(codigo_filho__icontains=termo_busca) |
                Q(descricao_filho__icontains=termo_busca)
            )

        filho_queryset = query.values(
            'codigo_filho', 
            'descricao_filho',
            'quantidade_necessaria_filho',
            'quantidade_em_op',
            'falta_produzir'
        ).order_by('codigo_filho')
        
        return list(filho_queryset)

    @classmethod
    def construir_arvore_projetos(cls, termo_busca: str = None) -> dict:
        """
        [DEPRECATED] Mantido temporariamente por compatibilidade.
        Busca os dados no banco e constrói o dicionário aninhado (VO -> Pai -> Filho).
        Retorna um dicionário ordenado para a View.
        """
        query = EstruturaProduto.objects.all().order_by('codigo_vo', 'codigo_pai', 'codigo_filho')

        if termo_busca:
            query = query.filter(
                Q(codigo_vo__icontains=termo_busca) |
                Q(descricao_vo__icontains=termo_busca) |
                Q(codigo_pai__icontains=termo_busca) |
                Q(descricao_pai__icontains=termo_busca) |
                Q(codigo_filho__icontains=termo_busca) |
                Q(descricao_filho__icontains=termo_busca)
            )

        arvore_projetos = {}

        for item in query:
            vo_key = item.codigo_vo

            if vo_key not in arvore_projetos:
                arvore_projetos[vo_key] = {
                    'descricao_vo': item.descricao_vo,
                    'pais': {}
                }

            pai_key = item.codigo_pai
            if pai_key not in arvore_projetos[vo_key]['pais']:
                arvore_projetos[vo_key]['pais'][pai_key] = {
                    'descricao_pai': item.descricao_pai,
                    'filhos': []
                }

            arvore_projetos[vo_key]['pais'][pai_key]['filhos'].append({
                'codigo_filho': item.codigo_filho,
                'descricao_filho': item.descricao_filho,
                'quantidade_necessaria_filho': item.quantidade_necessaria_filho,
                'quantidade_em_op': item.quantidade_em_op,
                'falta_produzir': item.falta_produzir,
            })

        return arvore_projetos

    @classmethod
    def gerar_dataframe_exportacao(cls, termo_busca: str = None) -> pd.DataFrame:
        """
        Busca os dados do banco, aplica o filtro (se existir)
        e gera um DataFrame limpo e traduzido pronto para exportação.
        """
        query = EstruturaProduto.objects.all().order_by('codigo_vo', 'codigo_pai', 'codigo_filho')

        if termo_busca:
            query = query.filter(
                Q(codigo_vo__icontains=termo_busca) |
                Q(descricao_vo__icontains=termo_busca) |
                Q(codigo_pai__icontains=termo_busca) |
                Q(codigo_filho__icontains=termo_busca) |
                Q(descricao_filho__icontains=termo_busca)
            )

        # Se não houver dados, retorna um DataFrame vazio
        if not query.exists():
            return pd.DataFrame()

        # Converte a QuerySet para DataFrame
        df = pd.DataFrame(list(query.values()))

        # Dicionário De-Para: 'Nome no Banco' : 'Nome legivel no Excel'
        mapeamento_colunas = {
            'codigo_vo': 'Código VO (Projeto)',
            'descricao_vo': 'Descrição VO',
            'codigo_pai': 'Código Pai (Conjunto)',
            'descricao_pai': 'Descrição Pai',
            'codigo_filho': 'Código Filho (Componente)',
            'descricao_filho': 'Descrição Filho',
            'quantidade_necessaria_filho': 'Qtd. Necessária Total',
            'quantidade_em_op': 'Qtd. Produção Planejada (OP)',
            'falta_produzir': 'Saldo (Falta Produzir)'
        }

        # Renomeia as colunas
        df = df.rename(columns=mapeamento_colunas)

        # Filtra o DataFrame para manter APENAS as colunas que acabamos de renomear
        # Isso descarta o ID, data_importacao, etc.
        colunas_finais = list(mapeamento_colunas.values())
        df = df[colunas_finais]

        return df