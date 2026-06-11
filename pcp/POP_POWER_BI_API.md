# POP - Conexao Power BI na API PCP

## Objetivo

Orientar o analista de dados do PCP a conectar o Power BI ao endpoint de movimentacoes de estoque do modulo PCP, transformar o JSON em tabela e manter a consulta adequada para atualizacao no Power BI Desktop e no Power BI Service.

## Dados da conexao

- Metodo: `GET`
- Endpoint: `/api/pcp/powerbi/movimentacoes/`
- Autenticacao: `Authorization: Api-Key <token>`
- Retorno: JSON paginado com `count`, `next`, `previous` e `results`
- Tamanho padrao da pagina: `5000`
- Tamanho maximo da pagina: `20000`

Campos retornados:

- `filial`
- `produto_codigo`
- `data_movimentacao`
- `tipo_movimentacao`
- `origem_movimentacao`
- `quantidade`
- `documento`
- `cf_operacao`

Filtros disponiveis:

- `data_inicio`: data inicial da movimentacao, formato `yyyy-mm-dd`
- `data_fim`: data final da movimentacao, formato `yyyy-mm-dd`
- `produto_codigo`: codigo exato do produto
- `filial`: filial exata
- `tipo_movimentacao`: tipo da movimentacao
- `origem_movimentacao`: origem da movimentacao

## Passo a passo no Power BI

1. Abra o Power BI Desktop.
2. Acesse `Obter dados` > `Consulta em branco`.
3. Clique em `Transformar dados`.
4. No Power Query, selecione a consulta criada.
5. Acesse `Pagina Inicial` > `Editor Avancado`.
6. Apague o conteudo padrao.
7. Cole o script M deste POP.
8. Ajuste `BaseUrl`, `ApiKey`, `DataInicio` e `DataFim`.
9. Clique em `Concluido`.
10. Na primeira execucao, configure a credencial como `Anonimo`.
11. Confirme que a tabela carregou com as colunas esperadas.
12. Ajuste os tipos de dados se necessario.
13. Clique em `Fechar e Aplicar`.

## Script padrao em Linguagem M

```powerquery
let
    BaseUrl = "https://SEU-DOMINIO.pythonanywhere.com",
    ApiKey = "COLE_AQUI_A_CHAVE_DA_API",
    RelativePath = "api/pcp/powerbi/movimentacoes/",
    PageSize = "20000",
    DataInicio = "2026-01-01",
    DataFim = Date.ToText(Date.From(DateTime.LocalNow()), "yyyy-MM-dd"),

    GetPage = (PageNumber as number) as record =>
        let
            Response =
                Json.Document(
                    Web.Contents(
                        BaseUrl,
                        [
                            RelativePath = RelativePath,
                            Query = [
                                page = Text.From(PageNumber),
                                page_size = PageSize,
                                data_inicio = DataInicio,
                                data_fim = DataFim
                            ],
                            Headers = [
                                Authorization = "Api-Key " & ApiKey,
                                Accept = "application/json"
                            ],
                            Timeout = #duration(0, 0, 2, 0)
                        ]
                    )
                ),
            Results = try Response[results] otherwise {},
            Count = try Response[count] otherwise List.Count(Results)
        in
            [
                Results = Results,
                Count = Count
            ],

    FirstPage = GetPage(1),
    TotalRows = FirstPage[Count],
    TotalPages = if TotalRows = 0 then 0 else Number.RoundUp(TotalRows / Number.FromText(PageSize)),
    OtherPageNumbers = if TotalPages > 1 then {2..TotalPages} else {},
    OtherPages = List.Transform(OtherPageNumbers, each GetPage(_)[Results]),
    AllPages = List.Combine({{FirstPage[Results]}, OtherPages}),
    Rows = List.Combine(AllPages),

    EmptyTable =
        #table(
            {
                "filial",
                "produto_codigo",
                "data_movimentacao",
                "tipo_movimentacao",
                "origem_movimentacao",
                "quantidade",
                "documento",
                "cf_operacao"
            },
            {}
        ),

    SourceTable =
        if List.IsEmpty(Rows)
        then EmptyTable
        else Table.FromRecords(Rows),

    TypedTable =
        Table.TransformColumnTypes(
            SourceTable,
            {
                {"filial", type text},
                {"produto_codigo", type text},
                {"data_movimentacao", type date},
                {"tipo_movimentacao", type text},
                {"origem_movimentacao", type text},
                {"quantidade", type number},
                {"documento", type text},
                {"cf_operacao", type text}
            },
            "pt-BR"
        )
in
    TypedTable
```

## Parametros recomendados

Crie parametros no Power Query para evitar editar o script diretamente:

- `pBaseUrl`: URL base do ERP, sem barra final.
- `pApiKey`: chave da API.
- `pDataInicio`: data inicial.
- `pDataFim`: data final.
- `pFilial`: filial opcional.

Exemplo de filtro opcional de filial:

```powerquery
QueryBase =
    [
        page = Text.From(PageNumber),
        page_size = PageSize,
        data_inicio = DataInicio,
        data_fim = DataFim
    ],

QueryParams =
    if pFilial = null or pFilial = ""
    then QueryBase
    else Record.AddField(QueryBase, "filial", pFilial)
```

Depois use `Query = QueryParams` dentro do `Web.Contents`.

## Boas praticas de performance

- Use filtro de periodo em toda consulta produtiva.
- Prefira `page_size = 20000` para reduzir chamadas HTTP, respeitando o limite da API.
- Use `BaseUrl` fixo com `RelativePath` e `Query` no `Web.Contents`; isso melhora a compatibilidade com atualizacao agendada.
- Nao use a URL completa de `next` como fonte de dados no Power Query. Controle a paginacao pelo parametro `page`.
- Defina tipos de dados no Power Query antes de carregar no modelo.
- Remova colunas nao utilizadas se a API for expandida no futuro.
- Evite transformacoes linha a linha pesadas no Power Query.
- Para historico grande, avalie atualizacao incremental no Power BI.
- Guarde a API key em parametro separado e restrinja o compartilhamento do PBIX.
- No Power BI Service, configure a credencial da fonte como `Anonimo`; o token segue no header.

## Tratamento de erros comuns

- `403`: chave ausente, invalida ou header fora do formato `Api-Key <token>`.
- Timeout: periodo muito grande ou pagina muito pesada. Reduza o intervalo de datas ou teste `page_size` menor.
- Tabela vazia: valide `data_inicio`, `data_fim`, `filial` e se ha movimentacoes no periodo.
- Erro de credencial no Service: revise se a fonte esta como `Anonimo`.

## Checklist para o analista PCP

- Recebi a URL base correta do ERP.
- Recebi a chave da API com o responsavel de TI.
- Configurei a consulta como `Anonimo`.
- Usei o endpoint `/api/pcp/powerbi/movimentacoes/`.
- Mantive o header `Authorization = "Api-Key " & ApiKey`.
- Apliquei filtro de periodo.
- Conferi `filial`, `produto_codigo`, `data_movimentacao` e `quantidade`.
- Validei uma amostra contra o ERP antes de publicar o relatorio.
- Configurei a atualizacao agendada apenas depois da validacao no Desktop.
