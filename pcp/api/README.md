# API PCP

## Escopo

Endpoints HTTP do modulo PCP. A API operacional atende telas e fluxos internos do ERP. O endpoint dedicado ao Power BI atende consumo analitico de movimentacoes de estoque.

Base path configurado no projeto:

```text
/api/pcp/
```

## Autenticacao

### API operacional

Requer usuario autenticado com acesso a um dos grupos:

- `PCP`
- `TI`
- `Diretoria`

Superusuarios tambem possuem acesso.

### API Power BI

Usa chave de API via header HTTP:

```text
Authorization: Api-Key <token>
```

O token esperado vem da variavel de ambiente:

```text
POWER_BI_API_KEY
```

## Endpoint Power BI

### Movimentacoes de estoque

```text
GET /api/pcp/powerbi/movimentacoes/
```

Retorna as movimentacoes de estoque estruturadas para consumo no Power BI.

Query params aceitos:

| Parametro | Tipo | Obrigatorio | Descricao |
| --- | --- | --- | --- |
| `data_inicio` | date `yyyy-mm-dd` | Nao | Filtra movimentacoes com data maior ou igual. |
| `data_fim` | date `yyyy-mm-dd` | Nao | Filtra movimentacoes com data menor ou igual. |
| `produto_codigo` | text | Nao | Filtra pelo codigo exato do produto. |
| `filial` | text | Nao | Filtra pela filial exata. |
| `tipo_movimentacao` | text | Nao | Filtra pelo tipo da movimentacao. |
| `origem_movimentacao` | text | Nao | Filtra pela origem da movimentacao. |
| `page` | number | Nao | Numero da pagina. |
| `page_size` | number | Nao | Registros por pagina. Padrao `5000`, maximo `20000`. |

Exemplo:

```text
GET /api/pcp/powerbi/movimentacoes/?data_inicio=2026-01-01&data_fim=2026-12-31&page=1&page_size=20000
Authorization: Api-Key <token>
Accept: application/json
```

Formato do retorno:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "filial": "01",
      "produto_codigo": "PROD-001",
      "data_movimentacao": "2026-06-03",
      "tipo_movimentacao": "ENTRADA",
      "origem_movimentacao": "NF_ENTRADA",
      "quantidade": 10,
      "documento": "123456",
      "cf_operacao": "1102"
    }
  ]
}
```

Campos retornados em `results`:

| Campo | Tipo esperado no Power BI |
| --- | --- |
| `filial` | Texto |
| `produto_codigo` | Texto |
| `data_movimentacao` | Data |
| `tipo_movimentacao` | Texto |
| `origem_movimentacao` | Texto |
| `quantidade` | Numero decimal |
| `documento` | Texto |
| `cf_operacao` | Texto |

## Endpoints operacionais

```text
GET  /api/pcp/areas/
POST /api/pcp/areas/

GET  /api/pcp/ativos/
POST /api/pcp/ativos/

GET  /api/pcp/planos-manutencao/
POST /api/pcp/planos-manutencao/

GET  /api/pcp/programacoes-manutencao/
POST /api/pcp/programacoes-manutencao/recalcular/

GET  /api/pcp/downtimes/
POST /api/pcp/downtimes/
POST /api/pcp/downtimes/<downtime_id>/fechar/

GET  /api/pcp/execucoes-manutencao/
POST /api/pcp/execucoes-manutencao/
POST /api/pcp/execucoes-manutencao/<execucao_id>/concluir/
```

### Downtimes

Tipos aceitos em `POST /api/pcp/downtimes/`:

| `tipo` | Categoria derivada pelo backend |
| --- | --- |
| `falta_mao_obra` | `tempo_producao_perdido` |
| `maquinario_estragou` | `tempo_producao_perdido` |
| `falta_material` | `tempo_producao_perdido` |
| `manutencao` | `tempo_producao_perdido` |
| `falta_desenho` | `tempo_ocioso` |

O campo `categoria` e somente leitura. Respostas de downtime incluem `categoria`,
`categoria_descricao` e `tipo_descricao`. O endpoint `GET /api/pcp/downtimes/`
aceita filtro por `categoria` e por `tipo`.

## Observacoes para consumo analitico

- Para Power BI, use apenas `GET /api/pcp/powerbi/movimentacoes/`.
- Prefira filtros de periodo para evitar carga historica desnecessaria.
- Nao exponha a chave `POWER_BI_API_KEY` em prints, documentacoes publicas ou arquivos compartilhados fora do time autorizado.
- No Power BI Service, configure a fonte como `Anonimo`; a autenticacao real ocorre pelo header `Authorization`.
