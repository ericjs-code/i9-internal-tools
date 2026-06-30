from decimal import Decimal
import unicodedata

from django.core.paginator import Paginator
from django.db.models import Max

from compras.models import ComprasSyncLog, PmsCustoTarefa, PmsEdt, PmsProjeto, PmsTarefa
from compras.services.pms_hierarchy import (
    calcular_indicadores_empenho,
    consolidar_custo_projeto,
    consolidar_custos_por_edt,
    montar_caminhos_edt,
)


ZERO = Decimal('0')
CATEGORIAS_PMS = (
    {
        'valor': 'materia_prima',
        'label': 'Mat\u00e9ria Prima',
        'termos': ('materia prima', 'materia-prima'),
    },
    {
        'valor': 'itens_comerciais',
        'label': 'Itens Comerciais',
        'termos': ('itens comerciais',),
    },
    {
        'valor': 'fixadores',
        'label': 'Fixadores',
        'termos': ('fixadores',),
    },
)
SITUACOES_FINANCEIRAS = {
    'sem_movimentacao': 'Sem movimentacao',
    'em_aberto': 'Em aberto',
    'totalmente_realizado': 'Totalmente realizado',
    'custo_sem_empenho': 'Custo sem empenho',
    'custo_acima_empenho': 'Custo acima do empenho',
}


class PmsDashboardSelector:
    @classmethod
    def get_context(cls, filtros=None):
        filtros = filtros or {}
        projetos_base = cls._projetos_base()
        lista_projetos = list(cls._lista_projetos(projetos_base))
        projetos_info = cls._mapa_projetos(projetos_base)
        projeto_filtro = filtros.get('projeto') or ''
        categorias_filtro = cls._normalizar_categorias_filtro(
            filtros.get('categorias')
            if 'categorias' in filtros
            else filtros.get('categoria')
        )
        revisao_filtro = cls._revisao_padrao(projetos_base, projeto_filtro)

        projeto = cls._get_projeto(projeto_filtro, revisao_filtro)
        edts = cls._listar_edts(projeto_filtro, revisao_filtro)
        tarefas = cls._enriquecer_tarefas_categoria(
            cls._listar_tarefas(projeto_filtro, revisao_filtro)
        )
        custos = cls._listar_custos(projeto_filtro, revisao_filtro)
        custos_carteira = cls._listar_custos_carteira(lista_projetos)
        tarefas_carteira = cls._enriquecer_tarefas_categoria(
            cls._listar_tarefas_carteira(lista_projetos)
        )

        if categorias_filtro:
            tarefas = cls._filtrar_tarefas_por_categoria(tarefas, categorias_filtro)
            custos = cls._filtrar_custos_por_tarefas(custos, tarefas)
            edts = cls._filtrar_edts_por_tarefas(edts, tarefas)
            tarefas_carteira = cls._filtrar_tarefas_por_categoria(
                tarefas_carteira,
                categorias_filtro,
            )
            custos_carteira = cls._filtrar_custos_por_tarefas(
                custos_carteira,
                tarefas_carteira,
            )

        custos_escopo = custos if projeto_filtro else custos_carteira
        tarefas_escopo = (
            tarefas
            if projeto_filtro
            else tarefas_carteira
        )

        custos_projeto = consolidar_custo_projeto(custos_escopo)
        custos_por_edt = consolidar_custos_por_edt(edts, tarefas, custos)
        caminhos_edt = montar_caminhos_edt(edts)
        linhas_hierarquia = cls._montar_linhas_hierarquia(
            edts=edts,
            tarefas=tarefas,
            custos=custos,
            custos_por_edt=custos_por_edt,
            caminhos_edt=caminhos_edt,
        )
        linhas_paginadas = cls._paginar_linhas(linhas_hierarquia, filtros.get('page'))

        return {
            'filtros': {
                'projeto': projeto_filtro,
                'categorias': categorias_filtro,
            },
            'lista_projetos': lista_projetos,
            'categorias_disponiveis': cls._categorias_disponiveis(),
            'projeto_atual': projeto,
            'modo_carteira': not projeto_filtro,
            'kpis': cls._montar_kpis(custos_projeto),
            'linhas_hierarquia': linhas_paginadas.object_list,
            'linhas_hierarquia_page': linhas_paginadas,
            'total_linhas_hierarquia': len(linhas_hierarquia),
            'grafico_custo_empenho': cls._grafico_custo_empenho(custos_escopo),
            'grafico_projetos': cls._grafico_projetos(custos_carteira, projetos_info),
            'grafico_edts': cls._grafico_edts(edts, custos_por_edt),
            'grafico_tarefas': cls._grafico_tarefas(custos_escopo, tarefas_escopo),
            'grafico_categorias': cls._grafico_categorias(
                custos_escopo,
                tarefas_escopo,
                categorias_filtro,
            ),
            'exportacao_csv': cls._preparar_exportacao(linhas_hierarquia),
            'ultima_sincronizacao': cls._ultima_sincronizacao(),
        }

    @staticmethod
    def _projetos_base():
        return PmsProjeto.objects.all().order_by('projeto', '-revisao')

    @staticmethod
    def _projeto_padrao(projetos_base):
        primeiro = projetos_base.first()
        return primeiro.projeto if primeiro else ''

    @staticmethod
    def _revisao_padrao(projetos_base, projeto):
        if not projeto:
            return ''
        revisao = (
            projetos_base
            .filter(projeto=projeto)
            .aggregate(revisao=Max('revisao'))
            .get('revisao')
        )
        return revisao or ''

    @staticmethod
    def _get_projeto(projeto, revisao):
        if not projeto or not revisao:
            return None
        return (
            PmsProjeto.objects
            .filter(projeto=projeto, revisao=revisao)
            .order_by('filial')
            .first()
        )

    @staticmethod
    def _listar_edts(projeto, revisao):
        if not projeto or not revisao:
            return []
        return list(
            PmsEdt.objects
            .filter(projeto=projeto, revisao=revisao)
            .order_by('nivel', 'ordem', 'edt')
            .values('filial', 'projeto', 'revisao', 'edt', 'edt_pai', 'descricao', 'nivel')
        )

    @staticmethod
    def _listar_tarefas(projeto, revisao):
        if not projeto or not revisao:
            return []
        return list(
            PmsTarefa.objects
            .filter(projeto=projeto, revisao=revisao)
            .order_by('edt', 'ordem', 'tarefa')
            .values(
                'filial',
                'projeto',
                'revisao',
                'edt',
                'tarefa',
                'descricao',
                'unidade',
                'quantidade',
                'data_inicio_prevista',
                'data_fim_prevista',
            )
        )

    @staticmethod
    def _listar_custos(projeto, revisao):
        if not projeto or not revisao:
            return []
        return list(
            PmsCustoTarefa.objects
            .filter(projeto=projeto, revisao=revisao)
            .order_by('edt', 'tarefa')
            .values(
                'filial',
                'projeto',
                'revisao',
                'edt',
                'tarefa',
                'custo_previsto',
                'custo_previsto_produtos',
                'custo_previsto_despesas',
                'custo_previsto_detalhado',
                'custo_realizado',
                'custo_empenhado',
                'saldo_previsto_realizado',
                'variacao_percentual',
            )
        )

    @staticmethod
    def _listar_custos_carteira(projetos):
        if not projetos:
            return []
        return list(
            PmsCustoTarefa.objects
            .filter(projeto__in=projetos)
            .order_by('projeto', 'revisao', 'edt', 'tarefa')
            .values(
                'filial',
                'projeto',
                'revisao',
                'edt',
                'tarefa',
                'custo_previsto',
                'custo_realizado',
                'custo_empenhado',
                'saldo_previsto_realizado',
            )
        )

    @staticmethod
    def _listar_tarefas_carteira(projetos):
        if not projetos:
            return []
        return list(
            PmsTarefa.objects
            .filter(projeto__in=projetos)
            .values('filial', 'projeto', 'revisao', 'edt', 'tarefa', 'descricao')
        )

    @staticmethod
    def _lista_projetos(projetos_base):
        return (
            projetos_base
            .values_list('projeto', flat=True)
            .distinct()
            .order_by('projeto')
        )

    @staticmethod
    def _mapa_projetos(projetos_base):
        projetos = {}
        for projeto in (
            projetos_base
            .values('projeto', 'descricao')
            .order_by('projeto', '-revisao')
        ):
            projetos.setdefault(projeto['projeto'], projeto.get('descricao') or '')
        return projetos

    @staticmethod
    def _categorias_disponiveis():
        return [
            {'valor': categoria['valor'], 'label': categoria['label']}
            for categoria in CATEGORIAS_PMS
        ]

    @staticmethod
    def _normalizar_texto(texto):
        texto = unicodedata.normalize('NFKD', texto or '')
        texto = ''.join(
            caractere
            for caractere in texto
            if not unicodedata.combining(caractere)
        )
        return texto.lower().strip()

    @classmethod
    def _categoria_tarefa(cls, descricao):
        descricao_normalizada = cls._normalizar_texto(descricao)
        for categoria in CATEGORIAS_PMS:
            if any(termo in descricao_normalizada for termo in categoria['termos']):
                return categoria['valor']
        return ''

    @staticmethod
    def _normalizar_categorias_filtro(categorias):
        if not categorias:
            return []
        if isinstance(categorias, str):
            categorias = [categorias]
        categorias_validas = {categoria['valor'] for categoria in CATEGORIAS_PMS}
        return [
            categoria
            for categoria in categorias
            if categoria in categorias_validas
        ]

    @classmethod
    def _enriquecer_tarefas_categoria(cls, tarefas):
        for tarefa in tarefas:
            tarefa['categoria'] = cls._categoria_tarefa(tarefa.get('descricao'))
        return tarefas

    @staticmethod
    def _chave_tarefa(item):
        return (
            item.get('filial'),
            item.get('projeto'),
            item.get('revisao'),
            item.get('tarefa'),
        )

    @staticmethod
    def _filtrar_tarefas_por_categoria(tarefas, categorias):
        categorias = set(categorias)
        return [
            tarefa
            for tarefa in tarefas
            if tarefa.get('categoria') in categorias
        ]

    @classmethod
    def _filtrar_custos_por_tarefas(cls, custos, tarefas):
        tarefas_validas = {cls._chave_tarefa(tarefa) for tarefa in tarefas}
        return [
            custo
            for custo in custos
            if cls._chave_tarefa(custo) in tarefas_validas
        ]

    @staticmethod
    def _filtrar_edts_por_tarefas(edts, tarefas):
        if not tarefas:
            return []

        edts_por_codigo = {edt['edt']: edt for edt in edts}
        codigos_necessarios = set()

        for tarefa in tarefas:
            codigo = tarefa.get('edt')
            while codigo and codigo not in codigos_necessarios:
                codigos_necessarios.add(codigo)
                codigo = (edts_por_codigo.get(codigo) or {}).get('edt_pai')

        return [
            edt
            for edt in edts
            if edt['edt'] in codigos_necessarios
        ]

    @staticmethod
    def _montar_kpis(custos_projeto):
        return {
            'custo': custos_projeto['custo'],
            'empenhado': custos_projeto['empenhado'],
            'saldo_empenho': custos_projeto['saldo_empenho'],
            'percentual_custo_empenhado': custos_projeto['percentual_custo_empenhado'],
            'custo_sem_empenho': custos_projeto['custo_sem_empenho'],
            'situacao_financeira': custos_projeto['situacao_financeira'],
            'custo_previsto': custos_projeto['custo_previsto'],
            'custo_realizado': custos_projeto['custo_realizado'],
            'custo_empenhado': custos_projeto['custo_empenhado'],
            'saldo_previsto_realizado': custos_projeto['saldo_previsto_realizado'],
            'percentual_realizado': custos_projeto['percentual_realizado'],
        }

    @classmethod
    def _montar_linhas_hierarquia(cls, edts, tarefas, custos, custos_por_edt, caminhos_edt):
        custos_por_tarefa = {item['tarefa']: item for item in custos}
        tarefas_por_edt = {}
        for tarefa in tarefas:
            tarefas_por_edt.setdefault(tarefa['edt'], []).append(tarefa)

        edts_por_codigo = {edt['edt']: edt for edt in edts}
        filhos_por_pai = {}
        for edt in edts:
            filhos_por_pai.setdefault(edt.get('edt_pai') or '', []).append(edt)

        linhas = []
        visitados = set()

        def adicionar_edt(edt, nivel_visual, ancestrais=None):
            ancestrais = ancestrais or []
            codigo_edt = edt['edt']
            if codigo_edt in visitados:
                return

            visitados.add(codigo_edt)
            custo_edt = custos_por_edt.get(codigo_edt, {})
            filhos = filhos_por_pai.get(codigo_edt, [])
            linhas.append({
                'tipo': 'edt',
                'projeto': edt['projeto'],
                'codigo': codigo_edt,
                'edt': codigo_edt,
                'edt_pai': edt.get('edt_pai') or '',
                'descricao': edt['descricao'],
                'nivel': edt['nivel'],
                'nivel_visual': nivel_visual,
                'parent_chain': '|'.join(ancestrais),
                'has_children': bool(filhos or tarefas_por_edt.get(codigo_edt)),
                'caminho': caminhos_edt.get(codigo_edt, codigo_edt),
                'custo_previsto': custo_edt.get('custo_previsto', ZERO),
                'custo_realizado': custo_edt.get('custo_realizado', ZERO),
                'custo_empenhado': custo_edt.get('custo_empenhado', ZERO),
                'saldo_previsto_realizado': custo_edt.get('saldo_previsto_realizado', ZERO),
                'percentual_realizado': custo_edt.get('percentual_realizado', ZERO),
                'custo': custo_edt.get('custo', ZERO),
                'empenhado': custo_edt.get('empenhado', ZERO),
                'saldo_empenho': custo_edt.get('saldo_empenho', ZERO),
                'percentual_custo_empenhado': custo_edt.get(
                    'percentual_custo_empenhado',
                    ZERO,
                ),
                'custo_sem_empenho': custo_edt.get('custo_sem_empenho', ZERO),
                'situacao_financeira': custo_edt.get(
                    'situacao_financeira',
                    'sem_movimentacao',
                ),
                'tarefas_count': custo_edt.get('tarefas_count', 0),
            })

            for filho in filhos:
                adicionar_edt(filho, nivel_visual + 1, ancestrais + [codigo_edt])

            for tarefa in tarefas_por_edt.get(codigo_edt, []):
                custo_tarefa = custos_por_tarefa.get(tarefa['tarefa'], {})
                linhas.append(cls._linha_tarefa(
                    tarefa,
                    custo_tarefa,
                    caminhos_edt.get(codigo_edt, codigo_edt),
                    nivel_visual + 1,
                    '|'.join(ancestrais + [codigo_edt]),
                ))

        raizes = [edt for edt in edts if not edt.get('edt_pai') or edt.get('edt_pai') not in edts_por_codigo]
        for edt in raizes:
            adicionar_edt(edt, 0)

        for edt in edts:
            adicionar_edt(edt, 0)

        return linhas

    @staticmethod
    def _linha_tarefa(tarefa, custo_tarefa, caminho_edt, nivel_visual, parent_chain):
        custo = custo_tarefa.get('custo_realizado', ZERO)
        empenhado = custo_tarefa.get('custo_empenhado', ZERO)
        indicadores_empenho = calcular_indicadores_empenho(
            custo,
            empenhado,
            custo if empenhado == ZERO else ZERO,
        )
        return {
            'tipo': 'tarefa',
            'projeto': tarefa['projeto'],
            'codigo': tarefa['tarefa'],
            'descricao': tarefa['descricao'],
            'edt': tarefa['edt'],
            'edt_pai': tarefa['edt'],
            'nivel_visual': nivel_visual,
            'parent_chain': parent_chain,
            'has_children': False,
            'caminho': caminho_edt,
            'unidade': tarefa['unidade'],
            'quantidade': tarefa['quantidade'],
            'data_inicio_prevista': tarefa['data_inicio_prevista'],
            'data_fim_prevista': tarefa['data_fim_prevista'],
            'categoria': tarefa.get('categoria', ''),
            'custo_previsto': custo_tarefa.get('custo_previsto', ZERO),
            'custo_previsto_produtos': custo_tarefa.get('custo_previsto_produtos', ZERO),
            'custo_previsto_despesas': custo_tarefa.get('custo_previsto_despesas', ZERO),
            'custo_previsto_detalhado': custo_tarefa.get('custo_previsto_detalhado', ZERO),
            'custo_realizado': custo_tarefa.get('custo_realizado', ZERO),
            'custo_empenhado': custo_tarefa.get('custo_empenhado', ZERO),
            'saldo_previsto_realizado': custo_tarefa.get('saldo_previsto_realizado', ZERO),
            'variacao_percentual': custo_tarefa.get('variacao_percentual', ZERO),
            'percentual_realizado': custo_tarefa.get('variacao_percentual', ZERO),
            **indicadores_empenho,
        }

    @staticmethod
    def _paginar_linhas(linhas, page_number):
        paginator = Paginator(linhas, 100)
        pagina = paginator.get_page(page_number or 1)
        ancestrais_necessarios = {
            codigo
            for linha in pagina.object_list
            for codigo in linha.get('parent_chain', '').split('|')
            if codigo
        }

        if not ancestrais_necessarios:
            return pagina

        inicio = pagina.start_index() - 1
        fim = pagina.end_index()
        pagina.object_list = [
            linha
            for indice, linha in enumerate(linhas)
            if inicio <= indice < fim
            or (
                linha.get('tipo') == 'edt'
                and linha.get('codigo') in ancestrais_necessarios
            )
        ]
        return pagina

    @staticmethod
    def _grafico_custo_empenho(custos):
        custo = sum((item['custo_realizado'] for item in custos), ZERO)
        empenhado = sum((item['custo_empenhado'] for item in custos), ZERO)
        return {
            'labels': ['Custo', 'Empenhado'],
            'tooltip_labels': ['Escopo / Total / Custo', 'Escopo / Total / Empenhado'],
            'data': [float(custo), float(empenhado)],
        }

    @staticmethod
    def _grafico_projetos(custos, projetos_info):
        por_projeto = {}
        for item in custos:
            projeto = item['projeto']
            totais = por_projeto.setdefault(projeto, {'custo': ZERO, 'empenhado': ZERO})
            totais['custo'] += item['custo_realizado']
            totais['empenhado'] += item['custo_empenhado']

        maiores = sorted(
            por_projeto.items(),
            key=lambda item: item[1]['custo'],
            reverse=True,
        )[:10]
        return {
            'labels': [projeto for projeto, _ in maiores],
            'tooltip_labels': [
                f'{projeto} / Projeto / {projetos_info.get(projeto, "") or projeto}'
                for projeto, _ in maiores
            ],
            'custo': [float(totais['custo']) for _, totais in maiores],
            'empenhado': [float(totais['empenhado']) for _, totais in maiores],
        }

    @staticmethod
    def _grafico_edts(edts, custos_por_edt):
        maiores_edts = []
        for edt in edts:
            codigo = edt['edt']
            custo = custos_por_edt.get(codigo, {})
            maiores_edts.append({
                'label': codigo,
                'projeto': edt['projeto'],
                'descricao': edt['descricao'],
                'valor': custo.get('custo', ZERO),
                'empenhado': custo.get('empenhado', ZERO),
            })

        maiores_edts = sorted(maiores_edts, key=lambda item: item['valor'], reverse=True)[:10]
        return {
            'labels': [item['label'] for item in maiores_edts],
            'tooltip_labels': [
                f'{item["projeto"]} / {item["label"]} / {item["descricao"] or item["label"]}'
                for item in maiores_edts
            ],
            'data': [float(item['valor']) for item in maiores_edts],
            'empenhado': [float(item['empenhado']) for item in maiores_edts],
        }

    @staticmethod
    def _grafico_tarefas(custos, tarefas):
        descricoes = {
            (
                item['filial'],
                item['projeto'],
                item['revisao'],
                item['tarefa'],
            ): {
                'descricao': item['descricao'],
                'edt': item.get('edt') or item['tarefa'],
            }
            for item in tarefas
        }
        por_tarefa = {}
        for item in custos:
            chave = (item['projeto'], item['tarefa'])
            totais = por_tarefa.setdefault(
                chave,
                {'custo': ZERO, 'empenhado': ZERO, 'descricao': '', 'nivel': item['tarefa']},
            )
            totais['custo'] += item['custo_realizado']
            totais['empenhado'] += item['custo_empenhado']
            chave_descricao = (
                item['filial'],
                item['projeto'],
                item['revisao'],
                item['tarefa'],
            )
            tarefa = descricoes.get(chave_descricao, {})
            totais['descricao'] = tarefa.get('descricao', totais['descricao'])
            totais['nivel'] = tarefa.get('edt', totais['nivel'])

        maiores = sorted(
            por_tarefa.items(),
            key=lambda item: item[1]['custo'],
            reverse=True,
        )[:10]
        return {
            'labels': [f'{projeto} / {tarefa}' for (projeto, tarefa), _ in maiores],
            'tooltip_labels': [
                f'{projeto} / {totais["nivel"]} / {totais["descricao"] or tarefa}'
                for (projeto, tarefa), totais in maiores
            ],
            'descricoes': [totais['descricao'] for _, totais in maiores],
            'custo': [float(totais['custo']) for _, totais in maiores],
            'empenhado': [float(totais['empenhado']) for _, totais in maiores],
        }

    @classmethod
    def _grafico_categorias(cls, custos, tarefas, categorias_filtro):
        tarefas_por_chave = {
            cls._chave_tarefa(tarefa): tarefa
            for tarefa in tarefas
        }
        totais_por_categoria = {
            categoria['valor']: {
                'label': categoria['label'],
                'custo': ZERO,
                'empenhado': ZERO,
            }
            for categoria in CATEGORIAS_PMS
        }

        for custo in custos:
            tarefa = tarefas_por_chave.get(cls._chave_tarefa(custo))
            categoria = (tarefa or {}).get('categoria')
            if categoria not in totais_por_categoria:
                continue
            totais_por_categoria[categoria]['custo'] += custo['custo_realizado']
            totais_por_categoria[categoria]['empenhado'] += custo['custo_empenhado']

        categorias = categorias_filtro or [categoria['valor'] for categoria in CATEGORIAS_PMS]
        itens = [
            totais_por_categoria[categoria]
            for categoria in categorias
            if categoria in totais_por_categoria
        ]

        return {
            'labels': [item['label'] for item in itens],
            'tooltip_labels': [
                f'Escopo / {item["label"]} / {item["label"]}'
                for item in itens
            ],
            'custo': [float(item['custo']) for item in itens],
            'empenhado': [float(item['empenhado']) for item in itens],
        }

    @classmethod
    def _preparar_exportacao(cls, linhas):
        return [
            {
                'projeto': linha.get('projeto', ''),
                'nivel_1': cls._nivel_exportacao(linha, 1),
                'nivel_2': cls._nivel_exportacao(linha, 2),
                'descricao': linha.get('descricao') or '',
                'custo': float(linha.get('custo', ZERO)),
                'empenhado': float(linha.get('empenhado', ZERO)),
                'saldo_empenhado': float(linha.get('saldo_empenho', ZERO)),
                'percentual_em_custo': float(linha.get('percentual_custo_empenhado', ZERO)),
                'situacao': SITUACOES_FINANCEIRAS.get(
                    linha.get('situacao_financeira'),
                    'Sem movimentacao',
                ),
            }
            for linha in linhas
        ]

    @staticmethod
    def _nivel_exportacao(linha, nivel):
        codigo_base = linha.get('edt') or linha.get('codigo') or ''
        partes = codigo_base.split('.')
        if len(partes) < nivel:
            return ''
        return '.'.join(partes[:nivel])

    @staticmethod
    def _ultima_sincronizacao():
        return (
            ComprasSyncLog.objects
            .filter(nome__in=['pms_dashboard', 'compras_pms'])
            .order_by('-iniciado_em')
            .first()
        )
