# README Técnico - Módulo RH

## 1. Visão geral do módulo

O módulo `rh` concentra funcionalidades de Recursos Humanos no sistema interno:

- Portal público de vagas e candidatura.
- Gestão interna de vagas e triagem de currículos.
- Solicitação e aprovação de abertura de vagas.
- Pesquisa demissional por link público com UUID.
- Formulário admissional por link público com UUID, dependentes, CSV e PDF.
- Cadastro/importação de funcionários e registros de ponto/absenteísmo.
- Dashboard de indicadores de RH.
- Avaliações de desempenho com competências, notas, ciência digital, CSV, PDF e dashboards.

Ele se encaixa no sistema principal por meio de `config/urls.py`, no prefixo `/rh/`, e usa autenticação, grupos e perfis organizacionais de apps compartilhados (`usuarios` e `core`).

## 2. Estrutura de arquivos

| Arquivo/pasta | Responsabilidade |
|---|---|
| `rh/models.py` | Define vagas, candidaturas, solicitações, pesquisas, formulários admissionais, funcionários, absenteísmo, competências e avaliações. |
| `rh/forms.py` | Centraliza forms internos e públicos, validações de formulário e formset de dependentes. |
| `rh/views.py` | Contém todas as function-based views do módulo, além de helpers de CSV, PDF, filtros e dashboards. |
| `rh/urls.py` | Mapeia as rotas do módulo para as views. |
| `rh/admin.py` | Configura administração Django dos models principais. |
| `rh/constants.py` | Lista UFs, órgãos expedidores, graus de parentesco e carrega municípios brasileiros via JSON. |
| `rh/services/avaliacoes_desempenho.py` | Regras de visibilidade, criação, edição e ciência das avaliações de desempenho. |
| `rh/management/commands/importar_ponto.py` | Comando antigo para importar ponto a partir de caminho local fixo. |
| `rh/management/commands/sincronizar_status_avaliacoes_desempenho.py` | Sincroniza status de avaliações conforme ciências registradas. |
| `rh/templates/rh/` | Telas HTML do módulo. |
| `static/rh/js/formulario_admissional.js` | Validação front-end do formulário admissional e inicialização de campos numéricos/telefones. |
| `rh/data_cities/municipios_brasil.json` | Base de municípios usada no campo `naturalidade`. |
| `rh/resources/municipios_brasil.json` | Arquivo JSON semelhante; não identificado uso direto no código atual. |
| `rh/migrations/` | Histórico de criação/evolução das tabelas e dados iniciais de competências. |

A relação principal é: `urls.py` aponta para `views.py`; as views instanciam `forms.py`, persistem `models.py` e renderizam templates em `templates/rh`. Validações críticas ficam em `forms.py` e algumas normalizações em `models.py`. PDFs e CSVs estão implementados diretamente em `views.py`.

## 3. Modelagem de dados

### `Vaga`

Representa uma vaga publicada ou fechada.

Campos principais:

- `titulo`, `setor`, `descricao`, `requisitos`.
- `ativa`: controla se a vaga aparece no portal público e aceita candidatura.
- `criada_por`: `ForeignKey` para o usuário autenticado, com `PROTECT`.
- `solicitacao_origem`: `OneToOneField` opcional para `SolicitacaoVaga`.

Choices:

- `SETORES`: Comercial, Compras, Diretoria, Financeiro, Obra, SGQ, Fábrica, Projetos, Engenharia, RH e TI.

### `Candidatura`

Representa uma inscrição em uma vaga.

Campos principais:

- `vaga`: `ForeignKey` para `Vaga`, com `PROTECT`.
- Dados pessoais básicos: `nome_completo`, `email`, `telefone`, `linkedin`.
- `curriculo`: arquivo em `curriculos/%Y/%m`, validado por `validar_curriculo`.
- `status`: Novo, Em Análise, Entrevista, Aprovado ou Reprovado/Banco de Talentos.
- `observacoes_rh`: anotações internas.
- `lgpd_consentimento`: existe no model, mas não está no `CandidaturaForm`; portanto não é preenchido pelo formulário público atual.

Validação de currículo:

- Máximo de 3 MB.
- Extensões aceitas: `.pdf`, `.doc`, `.docx`.

### `SolicitacaoVaga`

Representa uma requisição interna de contratação.

Campos principais:

- `solicitante`: usuário autenticado.
- Dados da vaga: departamento, nome, quantidade e data prevista.
- Motivo, possível substituído, perfil desejado e observações.
- `status`: `PENDENTE`, `APROVADA`, `REPROVADA`.
- `observacoes_rh`: parecer do RH.

Regra importante:

- A aprovação da solicitação não cria uma `Vaga` automaticamente. O template orienta o RH a publicar a vaga manualmente na gestão de vagas.

### `PesquisaDemissional`

Pesquisa enviada por link externo via UUID.

Campos principais:

- `id_pesquisa`: `UUIDField` primário.
- `gerada_por`: usuário que criou o link.
- `respondida` e `data_resposta`.
- Dados do ex-colaborador e do desligamento.
- Notas de liderança, oportunidade, reconhecimento, clima e recomendação.

Ciclo de vida:

1. RH gera link.
2. Ex-colaborador responde uma única vez.
3. Registro recebe `respondida=True` e `data_resposta`.
4. Reacesso ao link mostra tela de pesquisa já respondida.

### `FormularioAdmissional`

Formulário público de dados admissionais protegido por UUID.

Campos principais:

- Controle: `id_formulario`, `gerado_por`, `data_geracao`, `respondido`, `data_resposta`, `candidato_nome_interno`, `observacoes_rh`.
- Dados básicos, CTPS, endereço, contatos, documentos, estado civil, dependentes, uniforme, vale-transporte e LGPD.
- `telefone_principal` e `contato_recado` usam `PhoneNumberField(region='BR')`.

Normalização em `save()`:

- Remove caracteres não numéricos de CPF, CEP, PIS, CTPS, RG, título de eleitor e CNH.

Ciclo de vida:

1. RH gera link com nome interno.
2. Candidato preenche o link público.
3. Back-end valida campos obrigatórios, LGPD, telefone, vale-transporte e dependentes.
4. Salvamento ocorre em transação com `select_for_update`.
5. Registro fica bloqueado para nova resposta.

### `DependenteAdmissional`

Dependente vinculado ao formulário admissional.

Relacionamento:

- `formulario`: `ForeignKey` para `FormularioAdmissional`, `CASCADE`, `related_name='dependentes'`.

Normalização:

- Remove caracteres não numéricos do CPF no `save()`.

### `Funcionario`

Base de colaboradores usada no dashboard e absenteísmo.

Campos principais:

- `usuario`: `OneToOneField` opcional para o usuário do sistema.
- `cpf`: único, normalizado no `save()`.
- `matricula`: única, opcional.
- Datas de admissão/demissão, cargo, salário, situação e setor.

Situações:

- `AT`: Trabalhando.
- `DM`: Demitido.

### `CompetenciaDesempenho`

Competências avaliadas nas avaliações de desempenho.

Campos:

- `nome`, `descricao`, `ativa`, `ordem`.

Ordenação:

- `ordem`, depois `nome`.

Dados iniciais:

- Migration `0017_competencias_desempenho_iniciais.py` cadastra 9 competências padrão.

### `AvaliacaoDesempenho`

Avaliação por usuário, ano e ciclo.

Relacionamentos:

- `avaliado`: `ForeignKey` para usuário.
- `avaliada_por`: `ForeignKey` para usuário.
- `usuario_ciencia_gestor` e `usuario_ciencia_colaborador`: usuários que deram ciência.

Campos críticos:

- `ano`, `ciclo`, `status`, `comentarios`.
- Snapshot do avaliado: `nome_avaliado`, `cargo_avaliado`, `setor_avaliado`, `data_admissao_avaliado`.
- Ciência digital: flags, datas e usuários.

Constraints:

- `unique_together = ['avaliado', 'ano', 'ciclo']`.

Status:

- `RASCUNHO`
- `FINALIZADA`
- `CIENCIA_PENDENTE`
- `CIENCIA_PARCIAL`
- `CIENCIA_CONCLUIDA`
- `CANCELADA`

Regras calculadas:

- `media`: média das notas.
- `classificacao`: Excelente, Bom, Adequado com pontos de atenção, Abaixo do esperado ou Crítico.
- `status_calculado`: recalcula status com base nas ciências sem necessariamente persistir.

### `NotaCompetenciaDesempenho`

Nota de uma competência dentro de uma avaliação.

Relacionamentos:

- `avaliacao`: `ForeignKey`, `CASCADE`.
- `competencia`: `ForeignKey`, `PROTECT`.

Constraint:

- Uma nota por avaliação e competência (`unique_together`).

Validação:

- Nota deve estar entre 1 e 10.
- `save()` chama `full_clean()`.

### `RegistroAbsenteismo`

Registro mensal/por data de ponto vinculado a funcionário.

Campos:

- `funcionario`, `data_referencia`.
- `horas_normais`, `horas_falta`, `horas_extras`, `abono`.

Constraint:

- `unique_together = ['funcionario', 'data_referencia']`.

## 4. Fluxos principais do módulo

### Portal de vagas

1. `job_list` lista apenas `Vaga.ativa=True`.
2. `job_apply` recebe candidatura em vaga ativa.
3. `CandidaturaForm` valida dados e arquivo.
4. A candidatura é salva com status inicial `NO`.

### Gestão de vagas

1. `job_management` lista vagas com total de candidatos.
2. `job_form` cria ou edita vagas.
3. Em criação, `criada_por` recebe `request.user`.
4. Ativar/desativar vaga é feito pelo campo `ativa`.

Observação crítica: `job_form` exige login, mas não usa `group_required(['RH'])` no código atual.

### Triagem de candidatos

1. `candidate_screening` lista candidaturas, com filtro por `vaga`.
2. Mostra contadores de novos, em análise e entrevistas.
3. `candidate_datail` permite atualizar `status` e `observacoes_rh`.
4. Currículo é acessado pelo link do arquivo salvo.

### Solicitação de vaga

1. Usuário logado acessa `solicitar_abertura_vaga`.
2. `SolicitacaoVagaForm` valida campos.
3. Solicitação nasce como `PENDENTE`.
4. RH acessa `listar_solicitacoes`.
5. RH atualiza status e parecer em `detalhe_solicitacao`.

Não identificado no código atual: envio de notificação automática ao RH ou ao solicitante.

### Pesquisa demissional

1. RH gera link em `gerar_pesquisa`.
2. Link público aponta para `responder_pesquisa`.
3. Se já respondida, mostra tela de bloqueio.
4. Se válida, grava respostas, `respondida=True` e `data_resposta`.
5. `listar_pesquisas` exporta CSV com pesquisas respondidas.

### Formulário admissional

1. RH gera link em `gerar_formulario_admissional`.
2. Candidato responde em `responder_formulario_admissional`.
3. Form principal e formset de dependentes são validados.
4. Se `possui_dependentes_ir='SIM'`, pelo menos um dependente completo é exigido.
5. Se `utiliza_vale_transporte='SIM'`, trajeto é obrigatório.
6. Após salvar, o link não aceita nova resposta.
7. RH lista, detalha, exporta CSV e gera PDF se o formulário estiver respondido.

### Avaliação de desempenho

1. Usuário com permissão cria avaliação em `nova_avaliacao_desempenho`.
2. Form restringe avaliados por `usuarios_avaliaveis_para`.
3. Snapshot do avaliado é preenchido via `preencher_snapshot_avaliacao`.
4. Notas são salvas por competência ativa.
5. Edição passa por `pode_editar_avaliacao`.
6. Dashboard individual mostra média, pontos fortes, pontos de atenção e histórico.
7. Gestor e colaborador registram ciência via POST.
8. Status é atualizado conforme ciências.
9. CSV e PDF podem ser exportados.

### Dashboard RH

`dashboard_rh` calcula:

- Total de funcionários ativos.
- Admissões e desligamentos no ano.
- Turnover.
- Total de vagas, currículos, candidatos em processo, contratados e vagas abertas.
- Horas de falta, horas extras e média de faltas por colaborador.

Observação: o filtro de mês é lido, mas a variável filtrada não é usada no agregado final; o cálculo atual usa o ano inteiro.

### Importações

`importar_base_rh`:

- Aceita `.xls` e `.xlsx`.
- Lê via pandas.
- Atualiza/cria `Funcionario` por CPF.
- Usa nomes de colunas rígidos da planilha.

`importar_ponto_rh`:

- Aceita `.csv`.
- Exige `data_referencia`.
- Busca funcionário por matrícula (`Cod Epr`).
- Usa `convert_hours` de `core.utils.utils`.
- Atualiza/cria `RegistroAbsenteismo`.

`importar_empregados_avaliacao`:

- Importa a planilha de empregados ativos para a base de Avaliacao de Desempenho.
- Cria ou vincula `CustomUser`, `Funcionario`, `PerfilOrganizacional` e `VinculoAvaliacaoDesempenho`.
- Todos os usuarios novos recebem a senha padrao `tmg@2026` e ficam com `must_change_password=True`.
- Usuarios existentes, sem flags, nao tem senha nem `must_change_password` alterados.
- `--forcar-troca-senha-existentes` marca usuarios existentes vinculados com `must_change_password=True`, sem redefinir senha.
- `--atualizar-senha-existentes` redefine a senha dos usuarios existentes para a senha padrao e tambem marca `must_change_password=True`.
- O importador respeita a coluna `Gestor` da planilha como fonte principal do vinculo gestor/avaliado.
- Nao existe override manual para Gerson; Gerson deve seguir o gestor informado na planilha atual, hoje Danilo.

## 5. Regras de negócio

| Regra | Onde está |
|---|---|
| Vaga pública só aparece se `ativa=True`. | `job_list`, `job_apply`. |
| Candidatura só pode ser feita para vaga ativa. | `job_apply`. |
| Currículo tem limite de 3 MB e extensão PDF/Word. | `validar_curriculo` em `models.py`. |
| Solicitação de vaga inicia pendente. | Default do model `SolicitacaoVaga`. |
| Data prevista de admissão deve ser segunda-feira. | `SolicitacaoVagaForm.clean_data_prevista_inicio`. |
| Se o motivo for substituição, nome do substituído é obrigatório. | `SolicitacaoVagaForm.clean`. |
| Pesquisa demissional só pode ser respondida uma vez. | `responder_pesquisa`. |
| Formulário admissional só pode ser respondido uma vez. | `responder_formulario_admissional`. |
| Formulário admissional exige aceite LGPD. | `FormularioAdmissionalRespostaForm.clean_lgpd_consentimento`. |
| Telefone para recado não pode ser igual ao principal. | Form back-end e JS. |
| Vale-transporte exige trajeto quando marcado como Sim. | `FormularioAdmissionalRespostaForm.clean`. |
| Dependente parcialmente preenchido é inválido. | `DependenteAdmissionalForm.clean`. |
| Se houver dependentes IR, pelo menos um dependente completo é obrigatório. | `responder_formulario_admissional`. |
| Avaliação é única por avaliado, ano e ciclo. | Model e `AvaliacaoDesempenhoForm.clean`. |
| Nota de competência deve ser de 1 a 10. | `NotaCompetenciaDesempenho.clean` e `NotasCompetenciasDesempenhoForm`. |
| Avaliação precisa ter ao menos uma competência ativa. | `NotasCompetenciasDesempenhoForm.clean`. |
| Status de ciência é calculado pelas flags de ciência. | `AvaliacaoDesempenho.atualizar_status_ciencia`. |
| Colaborador só dá ciência na própria avaliação. | `pode_dar_ciencia_colaborador`. |
| Gestor só avalia/visualiza usuários em setores gerenciados, salvo acesso global. | `core.services.permissoes_organizacionais` e `rh.services.avaliacoes_desempenho`. |

Regras frágeis ou espalhadas:

- PDF/CSV e regras de dashboard estão dentro de `views.py`, que está muito grande.
- O mapeamento de setores de importação está hardcoded em `importar_base_rh`.
- `job_form` não tem restrição explícita ao grupo RH.
- Existe rota duplicada para `listar_pesquisas`: `pesquisa-demissional/` e `pesquisas/`.
- Há mensagens e textos com caracteres corrompidos em alguns arquivos, provavelmente por encoding histórico.

## 6. Permissões e controle de acesso

### Decorators usados

- `login_required`: exige autenticação.
- `group_required(['RH'])`: permite RH, superuser, TI e Diretoria.
- `exige_permissao(['rh'])`: traduz para grupo `RH` e usa `group_required`.

### Acesso global

Em `core.services.permissoes_organizacionais`, acesso global inclui grupos:

- `RH`
- `TI`
- `Diretoria`
- `superuser`

### Regras por tela

| Tela/fluxo | Permissão encontrada |
|---|---|
| Portal de vagas e candidatura | Público, sem login. |
| Triagem de candidatos | Login + grupo RH, com TI/Diretoria/superuser via decorator. |
| Gestão de vagas | Login + grupo RH. |
| Criar/editar vaga | Apenas login no código atual. Risco: falta `group_required(['RH'])`. |
| Solicitar vaga | Qualquer usuário logado. |
| Aprovar solicitações | Login + grupo RH. |
| Pesquisa demissional - gerar/listar | Login + grupo RH. |
| Pesquisa demissional - responder | Público via UUID. |
| Formulário admissional - gerar/listar/detalhar/PDF | Login + permissão RH. |
| Formulário admissional - responder | Público via UUID. |
| Dashboard RH/importações | Login + grupo RH. |
| Listar avaliações | Login; queryset limita visibilidade. |
| Criar avaliações | Acesso global ou gestor de setor. |
| Editar avaliações | Acesso global ou gestor do setor; bloqueia quando gestor e colaborador já deram ciência. |
| Ciência gestor | Acesso global ou gestor do setor. |
| Ciência colaborador | Somente usuário avaliado. |
| Dashboard geral de avaliações | Acesso global ou gestor. |

Riscos:

- `job_form` pode permitir criação/edição de vagas por qualquer usuário autenticado.
- Links públicos por UUID não exigem autenticação; isso é esperado pelo fluxo, mas exige cuidado com exposição do link.
- Exportações CSV/PDF contêm dados pessoais e admissionais sensíveis.

## 7. URLs e rotas

Prefixo global: `/rh/`.

| Rota | Nome | View |
|---|---|---|
| `vagas/` | `job_list` | Lista vagas públicas ativas. |
| `vagas/<pk>/aplicar/` | `job_apply` | Formulário público de candidatura. |
| `painel/` | `candidate_screening` | Painel interno de triagem. |
| `candidato/<pk>/` | `candidate_datail` | Detalhe e status da candidatura. |
| `gestao-vagas/` | `job_management` | Gestão interna de vagas. |
| `gestao-vagas/nova/` | `nova_vaga` | Criação de vaga. |
| `gestao-vagas/<pk>/editar/` | `editar_vaga` | Edição de vaga. |
| `solicitar-vaga/` | `solicitar_vaga` | Solicitação interna de contratação. |
| `solicitacoes/` | `listar_solicitacoes` | Lista solicitações para RH. |
| `solicitacoes/<pk>/` | `detalhe_solicitacao` | Parecer de solicitação. |
| `pesquisa-demissional/` | `listar_pesquisas` | Lista pesquisas. |
| `pesquisa-demissional/gerar/` | `gerar_pesquisa` | Gera link de pesquisa. |
| `pesquisa-demissional/responder/<uuid>/` | `responder_pesquisa` | Resposta pública. |
| `pesquisas/` | `listar_pesquisas` | Rota duplicada para lista de pesquisas. |
| `formulario-admissional/` | `listar_formularios_admissionais` | Lista formulários admissionais. |
| `formulario-admissional/gerar/` | `gerar_formulario_admissional` | Gera link admissional. |
| `formulario-admissional/<uuid>/` | `detalhe_formulario_admissional` | Detalhe interno. |
| `formulario-admissional/<uuid>/pdf/` | `exportar_formulario_admissional_pdf` | PDF admissional. |
| `formulario-admissional/responder/<uuid>/` | `responder_formulario_admissional` | Resposta pública. |
| `avaliacoes-desempenho/` | `listar_avaliacoes_desempenho` | Lista e exporta avaliações. |
| `avaliacoes-desempenho/dashboard-geral/` | `dashboard_geral_avaliacoes_desempenho` | Dashboard geral. |
| `avaliacoes-desempenho/nova/` | `nova_avaliacao_desempenho` | Criação de avaliação. |
| `avaliacoes-desempenho/<pk>/` | `detalhe_avaliacao_desempenho` | Detalhe simples. |
| `avaliacoes-desempenho/<pk>/editar/` | `editar_avaliacao_desempenho` | Edição. |
| `avaliacoes-desempenho/<pk>/dashboard/` | `dashboard_avaliacao_desempenho` | Dashboard individual. |
| `avaliacoes-desempenho/<pk>/ciencia-gestor/` | `dar_ciencia_gestor_avaliacao` | POST de ciência do gestor. |
| `avaliacoes-desempenho/<pk>/ciencia-colaborador/` | `dar_ciencia_colaborador_avaliacao` | POST de ciência do colaborador. |
| `avaliacoes-desempenho/<pk>/pdf/` | `exportar_pdf_avaliacao_desempenho` | PDF da avaliação. |
| `dashboard/` | `dashboard_rh` | Dashboard RH. |
| `dashboard/importar/` | `importar_base_rh` | Importação de base de funcionários. |
| `dashboard/importar-ponto/` | `importar_ponto_rh` | Importação de ponto. |

## 8. Views e responsabilidades

Todas as views do módulo são function-based views.

Responsabilidades principais:

- Recrutamento: `job_list`, `job_apply`, `candidate_screening`, `candidate_datail`, `job_management`, `job_form`.
- Solicitações: `solicitar_abertura_vaga`, `listar_solicitacoes`, `detalhe_solicitacao`.
- Pesquisas: `listar_pesquisas`, `gerar_pesquisa`, `responder_pesquisa`.
- Admissionais: `listar_formularios_admissionais`, `gerar_formulario_admissional`, `detalhe_formulario_admissional`, `exportar_formulario_admissional_pdf`, `responder_formulario_admissional`.
- Avaliações: listagem, criação, edição, detalhe, dashboards, ciências, CSV e PDF.
- Indicadores/importações: `dashboard_rh`, `importar_base_rh`, `importar_ponto_rh`.

Views com responsabilidade excessiva:

- `views.py` como um todo concentra muitos domínios.
- `exportar_formulario_admissional_pdf` e `exportar_pdf_avaliacao_desempenho` montam documentos inteiros dentro da view.
- `dashboard_geral_avaliacoes_desempenho` e `dashboard_rh` concentram agregações.
- Importações com pandas estão diretamente em views.

## 9. Forms e validações

### `CandidaturaForm`

Campos: nome, e-mail, telefone, LinkedIn e currículo.

Validação adicional vem do model para o arquivo.

### `VagaForm`

Campos: título, setor, descrição, requisitos e ativa.

Não identificado no código atual: validação específica além dos campos obrigatórios do model.

### `SolicitacaoVagaForm`

Exclui solicitante, data, status e parecer do RH.

Valida:

- Data prevista deve cair em uma segunda-feira.
- Motivo de substituição exige `nome_substituido`.

### `PesquisaDemissionalGeracaoForm`

Campos internos para o RH gerar link: ex-funcionário, setor, tipo de demissão, período de saída e tempo de casa.

### `PesquisaDemissionalRespostaForm`

Campos públicos de resposta.

Widgets:

- Notas de liderança/oportunidade/reconhecimento/clima: `min=1`, `max=5`.
- Recomendação: `min=0`, `max=10`.

Observação: no HTML o atributo `required` é definido no widget, mas os campos do model aceitam `blank=True/null=True`; a validação obrigatória depende do comportamento do form/widget e do navegador.

### `FormularioAdmissionalGeracaoForm`

Campo interno: `candidato_nome_interno`.

### `FormularioAdmissionalRespostaForm`

Validações importantes:

- Campos obrigatórios declarados em `campos_obrigatorios`.
- CPF com 11 dígitos.
- CEP com 8 dígitos.
- PIS com 11 dígitos.
- CTPS com máximo de 11 dígitos.
- Série CTPS com 4 dígitos quando preenchida.
- RG numérico com máximo de 9 dígitos.
- Título de eleitor com máximo de 12 dígitos.
- CNH com 9 dígitos quando preenchida.
- LGPD obrigatória.
- Trajeto obrigatório quando usa vale-transporte.
- Telefone de recado diferente do telefone principal.
- Naturalidade carregada de JSON de municípios.

Front-end:

- `static/rh/js/formulario_admissional.js` limita números, valida tamanhos e compara telefones.

Back-end:

- As mesmas regras principais são revalidadas no form, que é a camada confiável.

### `DependenteAdmissionalFormSet`

Cria até 2 linhas extras inicialmente e permite adicionar/remover.

Validação:

- Se qualquer campo de dependente for preenchido, todos devem ser preenchidos.
- CPF do dependente deve ter 11 dígitos quando preenchido.

### `AvaliacaoDesempenhoForm`

Campos: avaliado, ano, ciclo, status e comentários.

Valida:

- `avaliado` é limitado por `usuarios_avaliaveis_para`.
- Em edição, o avaliado fica desabilitado.
- Não permite duplicidade por avaliado, ano e ciclo.

### `NotasCompetenciasDesempenhoForm`

Gera campos dinâmicos para competências ativas.

Valida:

- Nota entre 1 e 10.
- Ao menos uma competência ativa cadastrada.

## 10. Templates e interface

Principais templates:

| Template | Função |
|---|---|
| `job_list.html` | Portal público de vagas, com cards e botão Aplicar. |
| `job_apply.html` | Envio de candidatura e currículo. |
| `job_management.html` | Gestão de vagas, contadores e atalhos para candidatos. |
| `job_form.html` | Criação/edição de vaga. |
| `candidate_screening.html` | Lista de candidaturas, filtro por vaga e contadores. |
| `candidate_datail.html` | Detalhe do candidato, link do currículo, status e observações. |
| `solicitar_vaga.html` | Formulário de solicitação de contratação. |
| `listar_solicitacoes.html` | Lista de solicitações, com pendentes em destaque. |
| `detalhe_solicitacao.html` | Parecer do RH e orientação para publicar vaga. |
| `listar_pesquisas.html` | Lista pesquisas, copia link e exporta CSV. |
| `gerar_pesquisa.html` | Geração de link de pesquisa demissional. |
| `responder_pesquisa.html` | Formulário público da pesquisa. |
| `pesquisa_sucesso.html` / `pesquisa_ja_respondida.html` | Feedback do link público. |
| `listar_formularios_admissionais.html` | Lista formulários, status, link externo, CSV e detalhe. |
| `gerar_formulario_admissional.html` | Geração de link admissional. |
| `responder_formulario_admissional.html` | Formulário público completo, dependentes e LGPD. |
| `detalhe_formulario_admissional.html` | Consulta interna completa e botão de PDF quando respondido. |
| `formulario_admissional_sucesso.html` / `formulario_admissional_ja_respondido.html` | Feedback do formulário público. |
| `listar_avaliacoes_desempenho.html` | Listagem, filtros, CSV, ações e usuários sem avaliação. |
| `form_avaliacao_desempenho.html` | Criação/edição de avaliação e notas. |
| `detalhe_avaliacao_desempenho.html` | Detalhe textual da avaliação. |
| `dashboard_avaliacao_desempenho.html` | Dashboard individual, ciências, PDF e gráficos. |
| `dashboard_geral_avaliacoes_desempenho.html` | Indicadores agregados, rankings e filtros. |
| `dashboard.html` | Dashboard RH geral e atalhos de importação. |
| `importar_base.html` | Upload de Excel de funcionários. |
| `importar_ponto.html` | Upload de CSV de ponto. |

Dependências de interface:

- Bootstrap e Bootstrap Icons são usados em templates.
- `responder_formulario_admissional.html` carrega Bootstrap via CDN e o JS local `rh/js/formulario_admissional.js`.
- Templates de avaliação usam dados preparados para gráficos; uso de biblioteca de gráficos aparece nos templates de dashboard.

## 11. Serviços, utils e funções auxiliares

### `rh/services/avaliacoes_desempenho.py`

Funções:

- `avaliacoes_visiveis_para(user)`: queryset por acesso global, gestor ou colaborador.
- `pode_criar_avaliacao(user)`: acesso global ou gestor.
- `pode_editar_avaliacao(user, avaliacao)`: acesso global ou gestor do setor; bloqueia avaliação com ambas as ciências.
- `pode_dar_ciencia_gestor(user, avaliacao)`: acesso global ou gestor do setor.
- `pode_dar_ciencia_colaborador(user, avaliacao)`: apenas o próprio avaliado.
- `preencher_snapshot_avaliacao(avaliacao)`: copia nome/cargo/setor/data de admissão do usuário/perfil organizacional.

### Helpers em `views.py`

- `_dependentes_texto`: serializa dependentes para CSV/PDF.
- `_nome_arquivo_formulario` e `_nome_arquivo_avaliacao`: geram nomes seguros.
- `_aplicar_filtros_avaliacoes_desempenho`: aplica filtros GET.
- `_salvar_notas_desempenho`: cria/atualiza notas em transação.
- `_dados_dashboard_avaliacao`: prepara métricas, histórico e flags de ação.
- Helpers de PDF: `_paragraph`, `_tabela_pdf`, `_grafico_barras_pdf`, `_grafico_medias_pdf`, `_assinaturas_pdf`, `_ciencia_pdf`.
- `_exportar_avaliacoes_desempenho_csv`: gera CSV de avaliações.
- `_usuarios_sem_avaliacao_context`: lista avaliáveis sem avaliação no ano/ciclo.

### Utils externos

- `core.utils.utils.convert_hours`: usado na importação de ponto.
- `core.services.permissoes_organizacionais`: base das regras de acesso organizacional.

## 12. Integrações com outros módulos

| Módulo | Integração |
|---|---|
| `usuarios` | Usa `settings.AUTH_USER_MODEL` para usuários, grupos e perfis. |
| `core.models` | Usa `SetorOrganizacional`, `PerfilOrganizacional` e `GestorSetor` indiretamente. |
| `core.decorators` | Usa `group_required` e `exige_permissao`. |
| `core.services.permissoes_organizacionais` | Define acesso global, gestores, usuários visíveis e avaliáveis. |
| `core.utils.utils` | Converte horas da importação de ponto. |
| `static/img/logo.jpg` | Usado em PDFs. |
| `config/urls.py` | Inclui o módulo em `/rh/`. |
| `core/templates/base.html` | Menu lateral do RH e atalhos. |

Impactos:

- Alterações em grupos (`RH`, `TI`, `Diretoria`) afetam acesso.
- Alterações em `PerfilOrganizacional`, `SetorOrganizacional` ou `GestorSetor` afetam avaliações.
- Alterações em `AUTH_USER_MODEL` ou nomes de grupos afetam quase todo o módulo.
- Remover/renomear `static/img/logo.jpg` altera PDFs.

## 13. Banco de dados e migrations

Tabelas principais esperadas:

- `rh_vaga`
- `rh_candidatura`
- `rh_solicitacaovaga`
- `rh_pesquisademissional`
- `rh_formularioadmissional`
- `rh_dependenteadmissional`
- `rh_funcionario`
- `rh_registroabsenteismo`
- `rh_competenciadesempenho`
- `rh_avaliacaodesempenho`
- `rh_notacompetenciadesempenho`

Migrations relevantes:

- `0001_initial`: cria vagas e candidaturas.
- `0002`: adiciona LGPD em candidatura.
- `0003` a `0006`: evoluem solicitações, vagas, currículos, status e setores.
- `0007`: ajustes em pesquisa demissional.
- `0009` e `0010`: funcionário, matrícula e absenteísmo.
- `0011` a `0015`: formulário admissional e dependentes.
- `0016`: cria avaliação de desempenho, competências e notas.
- `0017`: cadastra competências iniciais.
- `0018` e `0019`: evoluem avaliação.
- `0020`: migra avaliação para usuário, snapshot e ciência digital.

Cuidados em produção:

- Campos únicos (`cpf`, `matricula`, avaliação por ano/ciclo) podem falhar em dados duplicados.
- Mudanças em choices precisam considerar registros existentes.
- Alterações em `FormularioAdmissional` envolvem dados pessoais sensíveis.
- Alterar `CompetenciaDesempenho.ordem` impacta CSV, PDF e dashboards.
- Migrations de avaliação já possuem transformação de dados; testar em cópia antes de produção.

## 14. Pontos de manutenção

| Necessidade | Onde alterar |
|---|---|
| Adicionar campo em vaga | `models.py`, `forms.py`, `job_form.html`, migrations e possivelmente admin. |
| Alterar status de candidatura | `Candidatura.STATUS`, templates de triagem/detalhe e relatórios. |
| Alterar setores | `Vaga.SETORES`, importações e choices dependentes. |
| Alterar regra de solicitação | `SolicitacaoVagaForm` e templates relacionados. |
| Alterar formulário admissional | `FormularioAdmissional`, `FormularioAdmissionalRespostaForm`, templates, CSV e PDF. |
| Alterar dependentes | `DependenteAdmissional`, formset e template público/detalhe. |
| Alterar PDF admissional | `exportar_formulario_admissional_pdf`. |
| Alterar avaliação de desempenho | Models, forms, service `avaliacoes_desempenho.py`, templates e exports. |
| Alterar permissões de avaliação | `rh/services/avaliacoes_desempenho.py` e `core/services/permissoes_organizacionais.py`. |
| Alterar dashboard RH | `dashboard_rh` e `dashboard.html`. |
| Alterar importação de funcionários | `importar_base_rh`. |
| Alterar importação de ponto | `importar_ponto_rh` e `core.utils.utils.convert_hours`. |

## 15. Riscos técnicos e melhorias sugeridas

Riscos de segurança:

- `job_form` exige apenas login, sem grupo RH.
- Links públicos por UUID dão acesso a dados sensíveis de formulário/pesquisa se compartilhados indevidamente.
- CSV/PDF exportam dados pessoais e admissionais sem trilha de auditoria no código atual.
- Currículos ficam disponíveis via `curriculo.url`; controle depende da configuração de `MEDIA_URL/MEDIA_ROOT`.

Riscos de performance:

- `views.py` monta PDFs e CSVs de forma síncrona.
- Exportações CSV podem crescer sem paginação/streaming.
- Dashboard geral de avaliações converte querysets em lista e calcula rankings em memória.

Riscos de manutenção:

- `views.py` está muito grande e mistura regras, consultas, arquivos, PDF e HTML.
- Há duplicidade de helper `_valor_pdf`.
- `importar_base_rh` usa colunas e mapa de setores hardcoded.
- `importar_ponto.py` contém caminho absoluto local de outro ambiente.
- `dashboard_rh` lê `mes_filtro`, mas o agregado usa `registros_ponto_ano`.
- Textos com encoding corrompido dificultam manutenção.

Melhorias sugeridas:

- Extrair serviços de PDF, CSV, importação e dashboard.
- Criar testes unitários para forms e services de avaliação.
- Adicionar testes de permissão para cada rota sensível.
- Corrigir decorator de `job_form` se a regra esperada for apenas RH.
- Consolidar rotas duplicadas de pesquisa.
- Validar colunas obrigatórias antes de importar Excel/CSV.
- Avaliar storage privado para currículos e documentos sensíveis.
- Adicionar logs/auditoria para exportações e ciências digitais.

## 16. Checklist para futuras alterações

Antes de alterar:

- Confirmar regra de negócio com RH.
- Verificar impactos em models, forms, views, templates, admin, CSV e PDF.
- Mapear campos sensíveis e necessidade de LGPD.
- Verificar permissões por grupo e por perfil organizacional.
- Revisar migrations em ambiente de cópia.

Durante a alteração:

- Manter validação crítica no back-end.
- Atualizar templates e mensagens de erro.
- Atualizar CSV/PDF quando campos forem adicionados ou removidos.
- Garantir compatibilidade com dados existentes.
- Evitar alterar choices sem plano para registros antigos.

Testes manuais recomendados:

- Candidatar-se a uma vaga ativa com arquivo válido e inválido.
- Criar/editar/fechar vaga.
- Atualizar status de candidatura.
- Solicitar vaga com data em segunda-feira e fora de segunda-feira.
- Aprovar/reprovar solicitação.
- Gerar e responder pesquisa demissional; tentar responder novamente.
- Gerar formulário admissional, responder com e sem dependentes, exportar CSV/PDF.
- Criar avaliação, editar, registrar ciência do gestor e do colaborador.
- Exportar avaliação em CSV e PDF.
- Testar usuário RH, TI, Diretoria, gestor, colaborador e usuário comum.
- Importar base de funcionários e ponto com arquivo válido e inválido.

Antes de produção:

- Rodar migrations em ambiente de homologação.
- Validar permissões com contas reais de teste.
- Verificar geração de arquivos em ambiente semelhante ao produtivo.
- Conferir encoding dos arquivos de importação.
- Fazer backup antes de migrations que alteram dados.
