# Modulo PCP

## Arquitetura

O modulo segue um monolito modular Django:

- `models.py`: persistencia, relacionamentos e invariantes de banco.
- `services/`: comandos e regras de negocio transacionais.
- `selectors/`: consultas otimizadas para API e dashboard.
- `api/`: filtros, serializacao, permissoes e transporte HTTP.
- `tasks.py`: adaptadores Celery idempotentes.

Views, endpoints e tasks nao devem alterar models diretamente quando existir um service para a operacao.

## Invariantes principais

- Models principais utilizam soft delete por meio do campo `ativo`.
- Um ativo pode possuir apenas um downtime aberto.
- Todo downtime possui categoria macro derivada do tipo: tempo de producao perdido ou tempo ocioso.
- Tipos de downtime novos nao podem definir uma categoria incompativel.
- Um ativo pode possuir apenas uma execucao de manutencao aberta.
- Um plano pode possuir apenas uma programacao pendente.
- Programacoes atrasadas sao identificadas pela data prevista; o atraso nao e persistido como status.
- Movimentacoes de estoque sao unicas por filial, produto, data, tipo, origem, documento e CF.
- Alertas utilizam registro de envio para evitar duplicidade concorrente.
- Manutencoes concluidas preservam um snapshot documental do ativo e do plano.
- Evidencias de manutencao ficam fora do `MEDIA_ROOT` publico e possuem hash SHA-256.
- Eventos de auditoria sao imutaveis e nao utilizam soft delete.
- Alertas preventivos sao programados para 30, 15, 7 e 1 dia de antecedencia.

As invariantes criticas sao garantidas por constraints PostgreSQL e complementadas por services transacionais.

## Autorizacao

- Dashboard: grupos `PCP`, `TI`, `Diretoria` ou superusuario.
- API operacional: grupos `PCP`, `TI`, `Diretoria` ou superusuario.
- API Power BI: header `Authorization: Api-Key <token>`, configurado por `POWER_BI_API_KEY`.

## Documentacao da API

- Contrato tecnico da API: [`api/README.md`](api/README.md)
- POP para conexao no Power BI: [`POP_POWER_BI_API.md`](POP_POWER_BI_API.md)

## Tarefas Celery

- `pcp.run_pcp_estoque_etl`
- `pcp.recalcular_preventivas`
- `pcp.enviar_alertas_preventivas`
- `pcp.enviar_alertas_downtime_aberto`

As tasks utilizam retry com backoff. Como `CELERY_TASK_ACKS_LATE` esta habilitado, toda nova task do PCP deve ser idempotente.

## Configuracao

- `PCP_MAINTENANCE_ALERT_RECIPIENTS`: destinatarios dos alertas preventivos.
- `PCP_PRIVATE_MEDIA_ROOT`: diretorio privado das evidencias.
- `PCP_MAX_EVIDENCE_FILES`: limite de anexos por manutencao.
- `PCP_MAX_EVIDENCE_SIZE`: tamanho maximo de cada anexo em bytes.

O diretorio configurado em `PCP_PRIVATE_MEDIA_ROOT` nao deve ser publicado como Static File no PythonAnywhere.

## Validacao

Antes do deploy:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test pcp
```

O workflow de deploy executa essas validacoes em SQLite antes de atualizar o PythonAnywhere. As migrations de producao continuam destinadas ao PostgreSQL 12.

Para reiniciar os workers Celery apos o deploy, configure o secret `PA_ALWAYS_ON_TASK_IDS` no GitHub com os IDs das Always-on Tasks separados por virgula.
