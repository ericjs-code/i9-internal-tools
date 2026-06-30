from collections import defaultdict
from decimal import Decimal


ZERO = Decimal('0')
CEM = Decimal('100')


def _text(value):
    return str(value or '').strip()


def _decimal(value):
    if value is None or value == '':
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calcular_indicadores_empenho(custo, empenhado, custo_sem_empenho=ZERO):
    custo = _decimal(custo)
    empenhado = _decimal(empenhado)
    custo_sem_empenho = _decimal(custo_sem_empenho)
    saldo_empenho = empenhado - custo
    percentual_custo_empenhado = (custo / empenhado) * CEM if empenhado else ZERO

    if custo_sem_empenho > ZERO or (custo > ZERO and empenhado == ZERO):
        situacao_financeira = 'custo_sem_empenho'
    elif custo > empenhado:
        situacao_financeira = 'custo_acima_empenho'
    elif empenhado == ZERO and custo == ZERO:
        situacao_financeira = 'sem_movimentacao'
    elif custo == empenhado:
        situacao_financeira = 'totalmente_realizado'
    else:
        situacao_financeira = 'em_aberto'

    return {
        'custo': custo,
        'empenhado': empenhado,
        'saldo_empenho': saldo_empenho,
        'percentual_custo_empenhado': percentual_custo_empenhado,
        'custo_sem_empenho': custo_sem_empenho,
        'situacao_financeira': situacao_financeira,
    }


def montar_caminhos_edt(edts):
    por_codigo = {_text(edt.get('edt')): edt for edt in edts if _text(edt.get('edt'))}
    cache = {}

    def resolver(codigo):
        codigo = _text(codigo)
        if not codigo:
            return ''
        if codigo in cache:
            return cache[codigo]

        edt = por_codigo.get(codigo)
        if not edt:
            cache[codigo] = codigo
            return codigo

        pai = _text(edt.get('edt_pai'))
        if pai and pai != codigo and pai in por_codigo:
            caminho_pai = resolver(pai)
            caminho = f'{caminho_pai} > {codigo}' if caminho_pai else codigo
        else:
            caminho = codigo

        cache[codigo] = caminho
        return caminho

    for codigo in por_codigo:
        resolver(codigo)

    return cache


def montar_descendentes_edt(edts):
    filhos = defaultdict(list)
    codigos = []

    for edt in edts:
        codigo = _text(edt.get('edt'))
        if not codigo:
            continue
        codigos.append(codigo)
        filhos[_text(edt.get('edt_pai'))].append(codigo)

    def coletar(codigo):
        resultado = set()
        pilha = list(filhos.get(codigo, []))

        while pilha:
            atual = pilha.pop()
            if atual in resultado or atual == codigo:
                continue
            resultado.add(atual)
            pilha.extend(filhos.get(atual, []))

        return resultado

    return {codigo: coletar(codigo) for codigo in codigos}


def consolidar_custos_por_edt(edts, tarefas, custos):
    descendentes_por_edt = montar_descendentes_edt(edts)
    tarefa_para_edt = {
        _text(tarefa.get('tarefa')): _text(tarefa.get('edt'))
        for tarefa in tarefas
        if _text(tarefa.get('tarefa'))
    }

    custos_por_tarefa = {
        _text(custo.get('tarefa')): {
            'custo_previsto': _decimal(custo.get('custo_previsto')),
            'custo_realizado': _decimal(custo.get('custo_realizado')),
            'custo_empenhado': _decimal(custo.get('custo_empenhado')),
            'saldo_previsto_realizado': _decimal(custo.get('saldo_previsto_realizado')),
            **calcular_indicadores_empenho(
                custo.get('custo_realizado'),
                custo.get('custo_empenhado'),
                custo.get('custo_realizado')
                if _decimal(custo.get('custo_empenhado')) == ZERO
                else ZERO,
            ),
        }
        for custo in custos
        if _text(custo.get('tarefa'))
    }

    resultado = {}
    for edt in edts:
        codigo_edt = _text(edt.get('edt'))
        if not codigo_edt:
            continue

        edts_abrangidas = {codigo_edt, *descendentes_por_edt.get(codigo_edt, set())}
        tarefas_edt = [
            tarefa
            for tarefa, edt_tarefa in tarefa_para_edt.items()
            if edt_tarefa in edts_abrangidas
        ]

        previsto = ZERO
        realizado = ZERO
        empenhado = ZERO
        saldo = ZERO
        custo_sem_empenho = ZERO

        for tarefa in tarefas_edt:
            custo = custos_por_tarefa.get(tarefa, {})
            previsto += custo.get('custo_previsto', ZERO)
            realizado += custo.get('custo_realizado', ZERO)
            empenhado += custo.get('custo_empenhado', ZERO)
            saldo += custo.get('saldo_previsto_realizado', ZERO)
            custo_sem_empenho += custo.get('custo_sem_empenho', ZERO)

        percentual_realizado = ZERO
        if previsto:
            percentual_realizado = (realizado / previsto) * Decimal('100')

        indicadores_empenho = calcular_indicadores_empenho(
            realizado,
            empenhado,
            custo_sem_empenho,
        )
        resultado[codigo_edt] = {
            'custo_previsto': previsto,
            'custo_realizado': realizado,
            'custo_empenhado': empenhado,
            'saldo_previsto_realizado': saldo,
            'percentual_realizado': percentual_realizado,
            'tarefas_count': len(tarefas_edt),
            **indicadores_empenho,
        }

    return resultado


def consolidar_custo_projeto(custos):
    previsto = ZERO
    realizado = ZERO
    empenhado = ZERO
    saldo = ZERO
    custo_sem_empenho = ZERO

    for custo in custos:
        previsto += _decimal(custo.get('custo_previsto'))
        realizado += _decimal(custo.get('custo_realizado'))
        empenhado += _decimal(custo.get('custo_empenhado'))
        saldo += _decimal(custo.get('saldo_previsto_realizado'))
        if _decimal(custo.get('custo_empenhado')) == ZERO:
            custo_sem_empenho += _decimal(custo.get('custo_realizado'))

    percentual_realizado = ZERO
    if previsto:
        percentual_realizado = (realizado / previsto) * Decimal('100')

    indicadores_empenho = calcular_indicadores_empenho(
        realizado,
        empenhado,
        custo_sem_empenho,
    )
    return {
        'custo_previsto': previsto,
        'custo_realizado': realizado,
        'custo_empenhado': empenhado,
        'saldo_previsto_realizado': saldo,
        'percentual_realizado': percentual_realizado,
        **indicadores_empenho,
    }
