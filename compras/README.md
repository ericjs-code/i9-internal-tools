# Modulo de Compras

## Objetivo

O modulo atende dois fluxos independentes:

- Dashboard financeiro PMS por Projeto > EDT/WBS > Tarefa.
- Operacao de compras e avaliacao de fornecedores baseadas em solicitacoes e pedidos.

Os dados do Protheus sao lidos dos arquivos de spool e materializados no banco
da aplicacao. O modulo nao escreve no banco Protheus e nao utiliza APSDU como API.

## Arquitetura

### Dashboard PMS

- `ComprasPmsETLService`: extrai, valida, transforma e persiste os dados PMS.
- `PmsDashboardSelector`: consolida custos e prepara o contexto de leitura.
- `PmsProjeto`, `PmsEdt`, `PmsTarefa` e `PmsCustoTarefa`: dados materializados.
- `ComprasSyncLog`: historico de execucao e diagnostico da carga PMS.

### Fontes PMS e Compras

| Spool | Uso no dashboard |
| --- | --- |
| `AF8` | Projeto, revisao, descricao e configuracao da estrutura. |
| `AFC` | EDT/WBS, EDT pai e nivel da estrutura. |
| `AF9` | Tarefa, EDT vinculada, quantidade e datas. |
| `AFA` | Planejamento de produtos mantido para compatibilidade da carga. |
| `AFB` | Planejamento de despesas mantido para compatibilidade da carga. |
| `AFG` | Vinculo entre solicitacao de compra, projeto, revisao e tarefa. |
| `SC7` | Pedidos de compra e valor empenhado por item. |
| `SD1` | Recebimentos/notas e valor realizado por item de pedido. |

### Rateio por tarefa

Uma solicitacao pode estar vinculada a mais de uma tarefa PMS. O valor do
pedido e do recebimento nao pode ser repetido integralmente em cada tarefa.

Para cada combinacao `filial + numero da SC + item da SC`, o peso da tarefa e:

```text
peso da tarefa = AFG_QUANT da tarefa / soma de AFG_QUANT do item da SC
```

O mesmo peso e aplicado aos pedidos SC7 e aos recebimentos SD1. A soma dos
valores rateados deve ser igual ao valor original do pedido ou recebimento.
Distribuicoes com quantidade total zero interrompem a carga.

## KPIs e colunas financeiras

Os KPIs superiores e as colunas da tabela usam as mesmas regras. O filtro de
projeto define o conjunto de tarefas considerado. A revisao PMS e resolvida
internamente pela aplicacao a partir da ultima revisao disponivel para o
projeto, pois a base atual nao sustenta esse filtro como criterio gerencial
confiavel. Sem projeto selecionado, os KPIs representam a carteira formada
pelos projetos canonicos da AF8. Projetos existentes apenas em tabelas
auxiliares nao entram nessa visao.

Os campos de custo previsto continuam materializados temporariamente para
compatibilidade e rollback, mas nao participam dos KPIs, graficos ou tabela. A
empresa ainda nao mantem esse planejamento preenchido de forma confiavel no PMS.

### Custo

Representa o valor dos recebimentos/notas vinculados aos itens de pedido.

```text
Custo da tarefa = soma de D1_TOTAL * peso da tarefa
Custo da EDT = soma do custo de suas tarefas e EDTs descendentes
Custo do projeto = soma do custo de todas as tarefas consideradas
```

### Empenhado

Representa o valor total dos pedidos de compra emitidos e vinculados a tarefa.

```text
Empenhado da tarefa = soma de C7_TOTAL * peso da tarefa
Empenhado da EDT = soma do empenhado de suas tarefas e EDTs descendentes
Empenhado do projeto = soma do empenhado de todas as tarefas
```

O empenhado inclui parcelas que ja foram recebidas. Ele representa o valor
comprometido nos pedidos, nao apenas o saldo pendente de recebimento.

### Saldo do empenho

Representa a parcela empenhada que ainda nao foi convertida em custo.

```text
Saldo do empenho = Empenhado - Custo
```

O saldo negativo nao e truncado. Ele indica que o custo superou o empenhado e
deve ser analisado quanto a frete, impostos, devolucoes, estornos ou divergencia
de integracao.

### Percentual convertido em custo

```text
Percentual convertido em custo = (Custo / Empenhado) * 100
```

Quando o empenhado e zero, o percentual permanece em zero para evitar divisao
por zero. Se existir custo nessa condicao, o valor e destacado no KPI `Custo sem
Empenho` e na situacao financeira da linha.

### Situacoes financeiras

- `Sem movimentacao`: custo e empenhado iguais a zero.
- `Em aberto`: existe saldo positivo do empenho.
- `Totalmente realizado`: custo igual ao empenhado e ambos maiores que zero.
- `Custo sem empenho`: existe custo e o empenhado e zero.
- `Custo acima do empenho`: custo maior que o empenhado.

### Colunas da estrutura

| Coluna | Significado |
| --- | --- |
| Estrutura | Codigo hierarquico da EDT/WBS ou da tarefa. |
| Descricao | Descricao cadastrada no PMS. |
| Custo | Valor recebido conforme SD1, rateado pela AFG. |
| Empenhado | Valor dos pedidos conforme SC7, rateado pela AFG. |
| Saldo do Empenho | Diferenca entre empenhado e custo. |
| % em Custo | Percentual do empenhado convertido em custo. |
| Situacao | Classificacao financeira da linha. |

As linhas de tarefa apresentam o valor direto. Cada EDT soma suas tarefas e
todas as EDTs descendentes. O projeto soma cada tarefa uma unica vez, evitando
dupla contagem entre niveis da arvore.

### Graficos e escopos

- Sem projeto selecionado: comparativo da carteira, Top 10 projetos e Top 10
  tarefas por custo.
- Com projeto selecionado: comparativo do projeto, Top 10 EDT/WBS, Top 10
  tarefas e tabela tree paginada.
- Os rankings exibem custo e empenhado lado a lado. Custo e empenhado nao sao
  partes de um mesmo total, por isso o comparativo utiliza barras.

### Fluxo legado operacional

- `ComprasETLService`: atualiza a fila operacional e gera
  `report_operacional.xlsx`.
- `OperacaoCompras`: tabela local usada pelas telas operacionais e de avaliacao.

O dashboard gerencial antigo, o model `DataWarehouseCompras` e o arquivo
`report_SC_x_PC.xlsx` foram removidos. A migration
`0009_delete_datawarehousecompras` conclui a remocao da tabela fisica. Antes de
aplica-la em producao, deve ser feito backup caso exista exigencia de retencao
dos dados antigos.

## Configuracao

As configuracoes devem ficar no `.env`. Use `.env.example` como referencia.

```dotenv
SFTP_HOST=
SFTP_PORT=
SFTP_USER=
SFTP_PASS=
SFTP_REMOTE_DIR=
COMPRAS_PMS_ARQUIVOS=af80101.sdb,afc0101.sdb,af90101.sdb,afa0101.sdb,afb0101.sdb,afg0101.sdb,sc70101.sdb,sd10101.sdb
```

Regras:

- Nunca versionar o `.env`.
- Nunca inserir usuario, senha, host ou porta diretamente no codigo.
- A conta de origem deve ter somente as permissoes necessarias para leitura.

## Comandos

### PMS

Validar arquivos e schema sem gravar no banco local:

```bash
python manage.py sync_pms_dashboard --dry-run
```

Executar a carga PMS:

```bash
python manage.py sync_pms_dashboard
```

### Legado operacional

Executar a carga das telas operacionais e de avaliacao:

```bash
python manage.py sync_compras_legacy
```

Os comandos PMS e legado utilizam locks independentes, compartilhados com seus
respectivos fluxos Celery. Uma segunda execucao do mesmo fluxo e recusada. O
lock e liberado apos sucesso ou falha e possui expiracao de seguranca.

A carga legada realiza full refresh somente nas tabelas locais do modulo. A
carga PMS atualiza somente as tabelas materializadas do dashboard financeiro.

## Agendamento no PythonAnywhere

Use Scheduled Tasks como fluxo principal. Exemplo com valores ficticios:

```bash
cd /home/<usuario>/<projeto> && /home/<usuario>/.virtualenvs/<venv>/bin/python manage.py sync_compras_legacy
```

```bash
cd /home/<usuario>/<projeto> && /home/<usuario>/.virtualenvs/<venv>/bin/python manage.py sync_pms_dashboard
```

Recomendacoes:

1. Agendar somente depois que o Protheus concluir a geracao dos arquivos spool.
2. Separar os comandos por uma janela suficiente para evitar disputa por SFTP,
   CPU e banco local.
3. Nao usar caminhos, usuarios ou horarios deste documento como valores reais.
4. Revisar periodicamente o log da Scheduled Task e o `ComprasSyncLog`.
5. Testar cada comando manualmente no console antes de ativar o agendamento.

## Atualizacao manual e rollback

Os botoes manuais sao contingencia e aparecem somente para usuarios `is_staff`.
O agendamento deve ser a rotina oficial.

Em caso de falha no agendamento:

1. Consultar o log da Scheduled Task.
2. Confirmar disponibilidade e atualizacao dos arquivos spool.
3. Executar o comando correspondente manualmente no console.
4. Usar o botao administrativo apenas quando o worker Celery estiver disponivel.
5. Nao executar duas cargas do mesmo fluxo ao mesmo tempo.

## Implantacao

```bash
python manage.py migrate
python manage.py check
python manage.py test compras
python manage.py sync_pms_dashboard --dry-run
```

A carga real deve ser executada somente depois da migracao, do check, dos testes
e da validacao do dry-run.

## Validacao funcional

- Confirmar o filtro de projeto e a selecao automatica da revisao PMS mais
  recente.
- Conferir a hierarquia Projeto > EDT/WBS > Tarefa.
- Comparar custo, empenhado, saldo do empenho e percentual com uma amostra do PMS.
- Conferir consolidacao de custos das EDTs filhas nas EDTs pais.
- Validar paginacao e expansao da arvore em projetos extensos.
- Confirmar que usuarios comuns nao visualizam botoes de sincronizacao.
- Confirmar que o fluxo operacional e as avaliacoes continuam disponiveis.
