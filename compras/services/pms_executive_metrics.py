from collections import defaultdict
from decimal import Decimal
from statistics import median


ZERO = Decimal('0')
CEM = Decimal('100')


class PmsExecutiveMetricsService:
    @classmethod
    def build(cls, custos, tarefas, edts, custos_temporais, projetos_info):
        projeto_stats = cls._projetos(custos, tarefas, edts, projetos_info)
        edt_stats = cls._edts(custos, tarefas, edts)
        tarefa_stats = cls._tarefas(custos, tarefas)
        temporal = cls._temporal(custos_temporais)
        dias_analise = temporal.pop('dias_analise', {})

        return {
            'kpis_executivos': cls._kpis(projeto_stats, edt_stats),
            'grafico_eficiencia': cls._grafico_eficiencia(projeto_stats),
            'analise_edts': cls._analise_edts(edt_stats, dias_analise),
            'pareto_projetos': cls._pareto(projeto_stats, 'projeto', 'descricao', limite=10),
            'pareto_edts': cls._pareto(edt_stats, 'edt', 'descricao', limite=10),
            'pareto_tarefas': cls._pareto(tarefa_stats, 'tarefa', 'descricao', limite=10),
            'matriz_risco': cls._matriz_risco(projeto_stats),
            'serie_temporal': temporal,
        }

    @classmethod
    def _projetos(cls, custos, tarefas, edts, projetos_info):
        tarefas_por_projeto = defaultdict(set)
        edts_por_projeto = defaultdict(set)

        for tarefa in tarefas:
            tarefas_por_projeto[tarefa.get('projeto')].add(tarefa.get('tarefa'))
        for edt in edts:
            edts_por_projeto[edt.get('projeto')].add(edt.get('edt'))

        projetos = {}
        for custo in custos:
            projeto = custo.get('projeto')
            item = projetos.setdefault(
                projeto,
                {
                    'projeto': projeto,
                    'descricao': projetos_info.get(projeto, '') or projeto,
                    'custo_previsto': ZERO,
                    'custo_realizado': ZERO,
                    'custo_empenhado': ZERO,
                    'tarefas_count': 0,
                    'edts_count': 0,
                },
            )
            item['custo_previsto'] += cls._decimal(custo.get('custo_previsto'))
            item['custo_realizado'] += cls._decimal(custo.get('custo_realizado'))
            item['custo_empenhado'] += cls._decimal(custo.get('custo_empenhado'))

        for projeto, item in projetos.items():
            item['tarefas_count'] = len(tarefas_por_projeto.get(projeto, set()))
            item['edts_count'] = len(edts_por_projeto.get(projeto, set()))
            item['valor_acima_empenho'] = max(
                item['custo_realizado'] - item['custo_empenhado'],
                ZERO,
            )
            item['percentual_acima_empenho'] = cls._percentual_acima_empenho(
                item['custo_realizado'],
                item['custo_empenhado'],
            )
            item['percentual_convertido'] = cls._percentual(
                item['custo_realizado'],
                item['custo_empenhado'],
            )
            item['custo_por_tarefa'] = (
                item['custo_realizado'] / item['tarefas_count']
                if item['tarefas_count']
                else item['custo_realizado']
            )
            item['volume'] = cls._volume_projeto(item)

        return list(projetos.values())

    @classmethod
    def _edts(cls, custos, tarefas, edts):
        tarefas_por_chave = {
            cls._chave_tarefa(tarefa): tarefa
            for tarefa in tarefas
        }
        edts_por_chave = {
            (edt.get('projeto'), edt.get('edt')): edt
            for edt in edts
        }
        tarefas_por_edt = defaultdict(set)
        for tarefa in tarefas:
            tarefas_por_edt[(tarefa.get('projeto'), tarefa.get('edt'))].add(tarefa.get('tarefa'))

        stats = {}
        for custo in custos:
            tarefa = tarefas_por_chave.get(cls._chave_tarefa(custo), {})
            projeto = custo.get('projeto')
            edt_codigo = custo.get('edt') or tarefa.get('edt') or ''
            edt = edts_por_chave.get((projeto, edt_codigo), {})
            chave = (projeto, edt_codigo)
            item = stats.setdefault(
                chave,
                {
                    'projeto': projeto,
                    'edt': edt_codigo,
                    'descricao': edt.get('descricao') or edt_codigo,
                    'custo_previsto': ZERO,
                    'custo_realizado': ZERO,
                    'custo_empenhado': ZERO,
                    'tarefas_count': 0,
                },
            )
            item['custo_previsto'] += cls._decimal(custo.get('custo_previsto'))
            item['custo_realizado'] += cls._decimal(custo.get('custo_realizado'))
            item['custo_empenhado'] += cls._decimal(custo.get('custo_empenhado'))

        total_realizado = sum((item['custo_realizado'] for item in stats.values()), ZERO)
        for chave, item in stats.items():
            item['tarefas_count'] = len(tarefas_por_edt.get(chave, set()))
            item['saldo_previsto_realizado'] = item['custo_previsto'] - item['custo_realizado']
            item['saldo_empenho'] = item['custo_empenhado'] - item['custo_realizado']
            item['percentual_convertido'] = cls._percentual(
                item['custo_realizado'],
                item['custo_empenhado'],
            )
            item['custo_sem_empenho'] = (
                item['custo_realizado']
                if item['custo_realizado'] and not item['custo_empenhado']
                else ZERO
            )
            item['participacao_custo'] = cls._percentual(
                item['custo_realizado'],
                total_realizado,
            )

        return list(stats.values())

    @classmethod
    def _tarefas(cls, custos, tarefas):
        tarefas_por_chave = {
            cls._chave_tarefa(tarefa): tarefa
            for tarefa in tarefas
        }
        stats = {}
        for custo in custos:
            tarefa = tarefas_por_chave.get(cls._chave_tarefa(custo), {})
            chave = (
                custo.get('projeto'),
                custo.get('tarefa'),
            )
            item = stats.setdefault(
                chave,
                {
                    'projeto': custo.get('projeto'),
                    'tarefa': custo.get('tarefa'),
                    'descricao': tarefa.get('descricao') or custo.get('tarefa'),
                    'custo_realizado': ZERO,
                    'custo_empenhado': ZERO,
                },
            )
            item['custo_realizado'] += cls._decimal(custo.get('custo_realizado'))
            item['custo_empenhado'] += cls._decimal(custo.get('custo_empenhado'))
        return list(stats.values())

    @classmethod
    def _temporal(cls, custos_temporais):
        por_mes = defaultdict(lambda: {'custo_realizado': ZERO, 'custo_empenhado': ZERO})
        por_edt = defaultdict(lambda: {'primeira': None, 'ultima': None})

        for item in custos_temporais:
            competencia = item.get('competencia')
            if not competencia:
                continue
            por_mes[competencia]['custo_realizado'] += cls._decimal(item.get('custo_realizado'))
            por_mes[competencia]['custo_empenhado'] += cls._decimal(item.get('custo_empenhado'))
            chave_edt = (item.get('projeto'), item.get('edt') or '')
            datas = por_edt[chave_edt]
            datas['primeira'] = min(filter(None, [datas['primeira'], competencia]))
            datas['ultima'] = max(filter(None, [datas['ultima'], competencia]))

        competencias = sorted(por_mes)
        realizado_acumulado = ZERO
        empenhado_acumulado = ZERO
        labels = []
        realizado = []
        empenhado = []
        realizado_acumulado_data = []
        empenhado_acumulado_data = []
        variacao_mensal = []
        media_movel = []
        custos_realizados = []

        for competencia in competencias:
            custo_mes = por_mes[competencia]['custo_realizado']
            empenho_mes = por_mes[competencia]['custo_empenhado']
            realizado_acumulado += custo_mes
            empenhado_acumulado += empenho_mes
            custos_realizados.append(custo_mes)
            labels.append(competencia.strftime('%m/%Y'))
            realizado.append(float(custo_mes))
            empenhado.append(float(empenho_mes))
            realizado_acumulado_data.append(float(realizado_acumulado))
            empenhado_acumulado_data.append(float(empenhado_acumulado))
            anterior = custos_realizados[-2] if len(custos_realizados) > 1 else ZERO
            variacao_mensal.append(float(custo_mes - anterior))
            janela = custos_realizados[-3:]
            media_movel.append(float(sum(janela, ZERO) / len(janela)))

        pico_indice = max(
            range(len(custos_realizados)),
            key=lambda indice: custos_realizados[indice],
            default=None,
        )
        dias_analise = {}
        for chave, datas in por_edt.items():
            if datas['primeira'] and datas['ultima']:
                dias_analise[chave] = max((datas['ultima'] - datas['primeira']).days + 30, 1)

        return {
            'disponivel': bool(competencias),
            'labels': labels,
            'realizado': realizado,
            'empenhado': empenhado,
            'realizado_acumulado': realizado_acumulado_data,
            'empenhado_acumulado': empenhado_acumulado_data,
            'variacao_mensal': variacao_mensal,
            'media_movel_3m': media_movel,
            'pico_gasto': {
                'competencia': labels[pico_indice] if pico_indice is not None else '',
                'valor': float(custos_realizados[pico_indice]) if pico_indice is not None else 0,
            },
            'dias_analise': dias_analise,
            'limite': (
                ''
                if competencias
                else 'Serie temporal indisponivel ate a proxima carga PMS com datas financeiras de SC7/SD1.'
            ),
        }

    @classmethod
    def _kpis(cls, projetos, edts):
        custos = [item['custo_realizado'] for item in projetos]
        maior_custo = max(projetos, key=lambda item: item['custo_realizado'], default={})
        maior_acima_empenho = max(
            projetos,
            key=lambda item: item['percentual_acima_empenho'],
            default={},
        )
        edt_critica = max(edts, key=lambda item: item['custo_realizado'], default={})
        media = sum(custos, ZERO) / len(custos) if custos else ZERO
        mediana = Decimal(str(median(custos))) if custos else ZERO
        fora_curva = [
            item for item in projetos
            if item['custo_realizado'] > mediana and item['percentual_acima_empenho'] > ZERO
        ]
        total_custo = sum(custos, ZERO)
        top_80 = cls._itens_ate_percentual(projetos, total_custo, Decimal('80'))

        return {
            'media_custo_por_projeto': media,
            'mediana_custo_por_projeto': mediana,
            'projeto_maior_custo': maior_custo,
            'projeto_maior_acima_empenho': maior_acima_empenho,
            'edt_mais_critica': edt_critica,
            'projetos_fora_curva': len(fora_curva),
            'maior_concentracao_custo': {
                'quantidade': len(top_80),
                'percentual': Decimal('80') if top_80 else ZERO,
            },
        }

    @classmethod
    def _grafico_eficiencia(cls, projetos):
        valores = [item['custo_realizado'] for item in projetos]
        media = sum(valores, ZERO) / len(valores) if valores else ZERO
        return {
            'datasets': [{
                'label': 'Projetos',
                'data': [
                    {
                        'x': float(item['volume']),
                        'y': float(item['custo_realizado']),
                        'projeto': item['projeto'],
                        'descricao': item['descricao'],
                        'custoPrevisto': float(item['custo_previsto']),
                        'custoEmpenhado': float(item['custo_empenhado']),
                        'percentualAcimaEmpenho': float(item['percentual_acima_empenho']),
                        'valorAcimaEmpenho': float(item['valor_acima_empenho']),
                        'custoPorTarefa': float(item['custo_por_tarefa']),
                        'outlier': item['custo_realizado'] > media and media > ZERO,
                    }
                    for item in projetos
                ],
            }],
        }

    @classmethod
    def _analise_edts(cls, edts, dias_por_edt):
        itens = sorted(edts, key=lambda item: item['custo_realizado'], reverse=True)[:10]
        for item in itens:
            dias = dias_por_edt.get((item['projeto'], item['edt']))
            item['burn_rate'] = item['custo_realizado'] / dias if dias else ZERO
        return itens

    @classmethod
    def _pareto(cls, itens, codigo_key, descricao_key, limite):
        ordenados = sorted(itens, key=lambda item: item['custo_realizado'], reverse=True)[:limite]
        total = sum((item['custo_realizado'] for item in itens), ZERO)
        acumulado = ZERO
        labels = []
        valores = []
        percentual_acumulado = []

        for item in ordenados:
            acumulado += item['custo_realizado']
            labels.append(item.get(codigo_key) or '')
            valores.append(float(item['custo_realizado']))
            percentual_acumulado.append(float(cls._percentual(acumulado, total)))

        return {
            'labels': labels,
            'valores': valores,
            'percentual_acumulado': percentual_acumulado,
            'tooltip_labels': [
                f'{item.get("projeto", "")} / {item.get(codigo_key, "")} / {item.get(descricao_key, "")}'
                for item in ordenados
            ],
        }

    @classmethod
    def _matriz_risco(cls, projetos):
        custos = [item['custo_realizado'] for item in projetos]
        impacto_corte = Decimal(str(median(custos))) if custos else ZERO
        acima_empenho_corte = ZERO
        quadrantes = defaultdict(int)
        pontos = []

        for item in projetos:
            alto_custo = item['custo_realizado'] >= impacto_corte and impacto_corte > ZERO
            acima_empenho = item['percentual_acima_empenho'] > acima_empenho_corte
            if alto_custo and acima_empenho:
                quadrante = 'alto_custo_acima_empenho'
            elif alto_custo:
                quadrante = 'alto_custo_dentro_empenho'
            elif acima_empenho:
                quadrante = 'baixo_custo_acima_empenho'
            else:
                quadrante = 'baixo_custo_dentro_empenho'
            quadrantes[quadrante] += 1
            pontos.append({
                'x': float(item['custo_realizado']),
                'y': float(item['percentual_acima_empenho']),
                'projeto': item['projeto'],
                'descricao': item['descricao'],
                'quadrante': quadrante,
            })

        return {
            'pontos': pontos,
            'impacto_corte': float(impacto_corte),
            'acima_empenho_corte': float(acima_empenho_corte),
            'quadrantes': dict(quadrantes),
        }

    @staticmethod
    def _decimal(value):
        if value is None or value == '':
            return ZERO
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @classmethod
    def _percentual(cls, valor, base):
        valor = cls._decimal(valor)
        base = cls._decimal(base)
        return (valor / base) * CEM if base else ZERO

    @classmethod
    def _percentual_acima_empenho(cls, realizado, empenhado):
        realizado = cls._decimal(realizado)
        empenhado = cls._decimal(empenhado)
        if realizado <= empenhado:
            return ZERO
        if not empenhado:
            return CEM
        return ((realizado - empenhado) / empenhado) * CEM

    @staticmethod
    def _chave_tarefa(item):
        return (
            item.get('filial'),
            item.get('projeto'),
            item.get('revisao'),
            item.get('tarefa'),
        )

    @staticmethod
    def _volume_projeto(item):
        if item['custo_previsto'] > ZERO:
            return item['custo_previsto']
        if item['tarefas_count']:
            return Decimal(item['tarefas_count'])
        if item['edts_count']:
            return Decimal(item['edts_count'])
        return ZERO

    @classmethod
    def _itens_ate_percentual(cls, itens, total, limite_percentual):
        if not total:
            return []
        acumulado = ZERO
        selecionados = []
        for item in sorted(itens, key=lambda item: item['custo_realizado'], reverse=True):
            if cls._percentual(acumulado, total) >= limite_percentual:
                break
            acumulado += item['custo_realizado']
            selecionados.append(item)
        return selecionados
