// rnc_dashboard.js
// Padrão de Arquitetura: IIFE (Immediately Invoked Function Expression) para não poluir o escopo global.

const RNCDashboard = (function() {
    // ESTADO PRIVADO DO MÓDULO
    let table = null;
    let choicesResp = null;
    const CONFIG = window.RNC_CONFIG;
    const TIPO_GALERIA = {
        NC: 'padrao',
        EFICACIA: 'eficacia'
    };


    // FUNÇÕES UTILITÁRIAS
    const util = {
        formatarDataBR: function(cell){
            let val = cell.getValue();
            if (!val) return "-";
            val = String(val).replace(/\//g, '-');
            if(val.includes('-')){
                let parts = val.split('-');
                if(parts[0].length === 4) return `${parts[2]}/${parts[1]}/${parts[0]}`;
            }
            return val;
        },
        formatarDataExcel: function(value, data, type, params, column){
            if (!value) return "";
            let val = String(value).replace(/\//g, '-');
            if(val.includes('-')){
                let parts = val.split('-');
                if(parts[0].length === 4) return `${parts[2]}/${parts[1]}/${parts[0]}`;
            }
            return val;
        },
        filtroMultiploExato: function(headerValue, rowValue, rowData, filterParams) {
            if (!headerValue) return true;
            if (!rowValue) return false;
            let termos = headerValue.split(',').map(t => t.trim().toLowerCase()).filter(t => t !== "");
            let valorCelula = String(rowValue).toLowerCase();
            return termos.some(termo => valorCelula === termo);
        },
        filtroDataBR: function(headerValue, rowValue){
            if(!headerValue) return true;
            if(!rowValue) return false;
            const formatado = util.formatarDataBR({getValue:()=>rowValue});
            return formatado.includes(headerValue.trim());
        }
    };

    // MÉTODOS DE INICIALIZAÇÃO
    const initChoices = function() {
        if(document.getElementById('edit_responsaveis')){
            choicesResp = new Choices('#edit_responsaveis', {
                removeItemButton: true,
                searchEnable: true,
                placeholderValue: 'Selecione os responsáveis...',
                searchPlaceholderValue: 'Pesquisar...',
                itemSelectText: '',
                noResultsText: 'Nenhum usuário encontrado',
            });
        }
    };

    // TABULATOR
    const initTabulator = function() {
        table = new Tabulator("#tabela-rnc", {
            ajaxURL: CONFIG.urls.listar,
            layout: "fitData",
            responsiveLayout: "collapse",
            pagination: "local",
            paginationSize: 15,
            initialSort: [{column: "id", dir: "desc"}],
            resizableColumns: true,
            movableColumns: true,

            columns: [
                {
                    title: "Ações", field: "acoes", visible: true, download: false, hozAlign: "center",
                    formatter: function(cell){
                        return `<button type="button" class="btn btn-sm btn-primary py-0 btn-editar-rnc" title="Editar RNC completo">
                                    <i class="bi bi-pencil-square"></i> Editar
                                </button>`;
                    },
                    cellClick: function(e, cell){
                        let dadosDaLinha = cell.getRow().getData();
                        ui.abrirModalEdicao(dadosDaLinha);
                    }
                },
                {title: "ID", field: "id", sorter: "number", headerFilter: "input", headerFilterFunc: util.filtroMultiploExato, frozen: false},
                {title: "Status", field: "status",
                 headerFilter: "list", headerFilterFunc: "in", headerFilterParams: {valuesLookup:true, clearable:true, multiselect:true},
                 editor: "list", editable: function(cell){ return CONFIG.isSGQ; },
                 editorParams: {values: ["Não iniciada", "Em andamento", "Concluído", "Registro preliminar", "Cancelado"]},
                 formatter: function(cell) {
                     let val = cell.getValue();
                     let color = "secondary";
                     if(val === "Em andamento") color = "primary";
                     if(val === "Concluído") color = "success";
                     if(val === "Fora dos trilhos") color = "danger";
                     if(val === "Registro preliminar") color = "warning text-dark";
                     return `<span class="badge bg-${color} w-100">${val}</span>`;
                 }
                },
                {title: "Registrador", field: "registrador", headerFilter: "list", headerFilterFunc: 'in', headerFilterParams: {valuesLookup: true, clearable: true, multiselect: true} },
                {title: "Detector", field: "detector",
                 headerFilter: "list", headerFilterFunc: "in", headerFilterParams: {valuesLookup:true, clearable:true, multiselect:true},
                 editor: "list", editable: function(cell){ return CONFIG.isSGQ; },
                 editorParams: {values: ["Cliente", "Interno", "Auditor Interno", "Auditor Externo", "Fornecedor"]}
                },
                {title: "Data Abertura", field: "data_abertura", accessorDownload: util.formatarDataExcel, headerFilter: "input", headerFilterFunc: util.filtroDataBR, formatter: util.formatarDataBR},
                {title: "Projeto", field: "projeto_cod",
                 headerFilter: "input", editor: "input", editable: function(cell){ return CONFIG.isSGQ; },
                 headerFilterFunc: function(headerValue, rowValue, rowData, filterParams) {
                     if (!headerValue) return true;
                     if (!rowValue) return false;
                     let termos = headerValue.split(',').map(termo => termo.trim().toLowerCase()).filter(termo => termo !== "");
                     let valorCelula = String(rowValue).toLowerCase();
                     return termos.some(termo => valorCelula.includes(termo));
                 }
                },
                {title: "Equipamento", field: "equipamento", headerFilter: "input", headerFilterFunc: 'in', headerFilterParams: {valuesLookup: true, clearable: true, multiselect: true},
                 editor: "list", editable: function(cell){ return CONFIG.isSGQ; }, editorParams: {valuesLookup: true, clearable: true} // 🟢 Edição Inline Liberada
                },
                {title: "Elemento Rastreador", field: "elemento_rastreador", headerFilter: "input", editor: "input", editable: function(cell){ return CONFIG.isSGQ; }},
                {title: "Local Detecção", field: "local", headerFilter: "list", headerFilterFunc: "in", headerFilterParams: {valuesLookup: true, clearable: true, multiselect: true},
                 editor: "list", editable: function(cell){ return CONFIG.isSGQ; }, editorParams: {valuesLookup: true, clearable: true} // 🟢 Edição Inline Liberada
                },
                {title: "Origem", field: "origem",
                    headerFilter: 'list', headerFilterFunc: 'in', headerFilterParams: {valuesLookup: true, clearable: true, multiselect: true},
                    formatter: "lookup", formatterParams: {
                        "CO": "Comercial", "PE": "Projeto / Engenharia", "FA": "Fabricação", "MC": "Montagem / Comissionamento", "SU": "Suprimentos", "RH": "RH", "FO": "Fornecedor", "SG": "Processo Interno SGQ", "GR": "Geral"
                    },
                    editor: "list", editable: function(cell){ return CONFIG.isSGQ; },
                    editorParams: {
                        values: { "CO": "Comercial", "PE": "Projeto / Engenharia", "FA": "Fabricação", "MC": "Montagem / Comissionamento", "SU": "Suprimentos", "RH": "RH", "FO": "Fornecedor", "SG": "Processo Interno SGQ", "GR": "Geral" }
                    }
                },
                {title: "Categoria", field: "categoria",
                    headerFilter: 'list', headerFilterFunc: 'in', headerFilterParams: {valuesLookup: true, clearable: true, multiselect: true},
                    formatter: "lookup", formatterParams: {
                        "CO": "Comercial", "PE": "Projeto / Engenharia", "PC": "PCP", "FA": "Fabricação", "MO": "Obra / Montagem", "MC": "Montagem / Comissionamento", "SU": "Suprimentos", "FO": "Fornecedor Externo", "EX": "Recebimento / Expedição", "QU": "Qualidade", "RH": "Recursos Humanos", "FI": "Financeiro", "SG": "SGQ", "PJ": "Planejamento / Cronograma", "PR": "Processo", "RC": "Requisitos contratuais", "RN": "Requisitos normas", "SI": "Sistema"
                    },
                    editor: "list", editable: function(cell){ return CONFIG.isSGQ; },
                    editorParams: {
                        values: { "CO": "Comercial", "PE": "Projeto / Engenharia", "PC": "PCP", "FA": "Fabricação", "MO": "Obra / Montagem", "MC": "Montagem / Comissionamento", "SU": "Suprimentos", "FO": "Fornecedor Externo", "EX": "Recebimento / Expedição", "QU": "Qualidade", "RH": "Recursos Humanos", "FI": "Financeiro", "SG": "SGQ", "PJ": "Planejamento / Cronograma", "PR": "Processo", "RC": "Requisitos contratuais", "RN": "Requisitos normas", "SI": "Sistema" }
                    }
                },
                {title: "Criticidade", field: "criticidade",
                    headerFilter: "list", headerFilterFunc: "in", headerFilterParams: {valuesLookup:true, clearable:true, multiselect:true},
                    editor: "list", editable: function(cell){ return CONFIG.isSGQ; }, editorParams: {values: ["Alto", "Médio", "Baixo"]}
                },
                {title: "Imagem NC", field: "qtd_imagens", hozAlign: "center", formatter: function(cell){
                    let qtd = cell.getValue();
                    if(qtd > 0) {
                        return `<button type="button" class="btn btn-sm btn-outline-primary py-0" style="font-size: 0.75rem;">
                                    <i class="bi bi-image"></i> (${qtd})
                                </button>`;
                    }
                    return "-";
                }, cellClick: function(e, cell){
                    let dados = cell.getRow().getData();
                    if(dados.qtd_imagens > 0){ ui.abrirGaleriaImagens(dados, TIPO_GALERIA.NC); }
                }},
                {title: "Descrição da não conformidade", field: "descricao", formatter: "textarea", editor: "textarea", headerFilter: "input", editable: function(cell){ return CONFIG.isSGQ; }},
                {title: "Correção Imediata", field: "correcao", formatter: "textarea", editor: "textarea", headerFilter: "input", editable: true},
                {title: "Causas Principais", field: "causas_principais", formatter: "textarea", editor: "textarea", headerFilter: "input", editable: true},
                {title: "Ação Corretiva", field: "acao_corretiva", formatter: "textarea", editor: "textarea", headerFilter: "input", editable: true},
                {title: "Eficácia (Texto)", field: "eficacia_texto", formatter: "textarea", editor: "textarea", headerFilter: "input", editable: function(cell){ return CONFIG.isSGQ; }},
                {title: "Responsavel", field: "responsaveis",
                headerFilter: "list",
                    headerFilterFunc: function(headerValue, rowValue, rowData, filterParams) {
                        if (!headerValue || headerValue.length === 0) return true;
                        if (!rowValue) return false;
                        let textoCelula = String(rowValue);
                        return headerValue.some(nomeSelecionado => textoCelula.includes(nomeSelecionado));
                    },
                    headerFilterParams: { values: CONFIG.dadosSistema.listaTodosUsuarios, valuesLookup: true, clearable: true, multiselect: true }
                },
                {title: "Data Previsão Conclusão", field: "data_prevista_conclusao", accessorDownload: util.formatarDataExcel, headerFilter: "input", headerFilterFunc: util.filtroDataBR, formatter: util.formatarDataBR, editor: "date", editable: function(cell){ return CONFIG.isSGQ; }, editorParams:{ format:"yyyy-MM-dd" }},
                {title: "Data Encerramento", field: "data_encerramento", accessorDownload: util.formatarDataExcel, headerFilter: "input", headerFilterFunc: util.filtroDataBR, formatter: util.formatarDataBR, editor: "date", editable: function(cell){ return CONFIG.isSGQ; }, editorParams:{ format:"yyyy-MM-dd" }},
                {title: "Ishikawa", field: "ishikawa_link", editable: true, formatter: function(cell){
                let url = cell.getValue();
                if(url) return `<a href="${url}" target="_blank" class="text-primary text-decoration-none">Acessar</a>`;
                return "-";
                }},
                {title: "Evidência Eficácia PDF", download: false, field: "pdfs_dados", formatter: function(cell){
                    let pdfs = cell.getValue();
                    let rncId = cell.getRow().getData().id;

                    if(Array.isArray(pdfs) && pdfs.length > 0) {


                        let htmlBotoes = pdfs.map(pdfObj => {
                            return `
                                <div class="d-flex gap-1 mb-1">
                                    <a href="${pdfObj.url}" target="_blank" class="btn btn-sm btn-outline-danger py-0" title="Ver PDF" style="font-size: 0.75rem;">
                                        <i class="bi bi-file-pdf"></i> PDF
                                    </a>
                                    <button type="button" class="btn btn-sm btn-danger py-0" title="Excluir PDF" style="font-size: 0.75rem;" 
                                            onclick="RNCDashboard.api.deletarMidia('pdf', ${pdfObj.id}, ${rncId}, this)">
                                        <i class="bi bi-trash"></i>
                                    </button>
                                </div>
                            `;
                        }).join('');

                        return `<div class="d-flex flex-column align-items-center">${htmlBotoes}</div>`;
                    }
                    return "-";
                }},
                {title: "Imagem NC", field: "qtd_imagens", hozAlign: "center", formatter: function(cell){
                    let qtd = cell.getValue();
                    if(qtd > 0) {
                        return `<button type="button" class="btn btn-sm btn-outline-primary py-0" style="font-size: 0.75rem;">
                                    <i class="bi bi-image"></i> (${qtd})
                                </button>`;
                    }
                    return "-";
                }, cellClick: function(e, cell){
                    let dados = cell.getRow().getData();
                    if(dados.qtd_imagens > 0){ ui.abrirGaleriaImagens(dados, TIPO_GALERIA.NC); }
                }},
            ],
            locale: "pt-br",
            langs: {
                "pt-br": { pagination: { first: "Primeira", last: "Última", prev: "Anterior", next: "Próxima" } }
            }
        });

        table.on("cellEdited", api.atualizarInline);
    };

    // CAMADA DE API (FETCH)
    const api = {
        // CONFIRMAÇÃO DE SALVAMENTO INCORPORADA COM SWEETALERT
        atualizarInline: function (cell) {
            let id_rnc = cell.getRow().getData().id;
            let campo_editado = cell.getField();
            let novo_valor = cell.getValue();
            let valor_antigo = cell.getOldValue();

            // Evita requisição desnecessária se nada mudou
            if (novo_valor === valor_antigo) return;

            // Função interna para efetuar o fetch
            const dispararFetch = () => {
                fetch(`${CONFIG.urls.atualizarInlineBase}${id_rnc}/atualizar/`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': CONFIG.tokens.csrf},
                    body: JSON.stringify({campo: campo_editado, valor: novo_valor})
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'sucesso') {
                        // Efeito visual de sucesso ("pisca verde e apaga")
                        cell.getElement().style.transition = "background-color 0.5s ease";
                        cell.getElement().style.backgroundColor = "#d1e7dd";
                        setTimeout(() => { cell.getElement().style.backgroundColor = ""; }, 1500);
                    } else {
                        Swal.fire("Acesso Negado!", data.mensagem, "error");
                        cell.restoreOldValue();
                    }
                })
                .catch(error => {
                    Swal.fire("Erro de Rede", "Não foi possível conectar ao servidor.", "error");
                    cell.restoreOldValue();
                });
            };

            // Detecta se o usuário apagou o campo (ex: clicou fora sem selecionar nada)
            if (novo_valor === "" || novo_valor === null || novo_valor === undefined) {
                Swal.fire({
                    title: 'Atenção!',
                    text: 'Você apagou o valor desta célula. Tem certeza que deseja salvar como vazio?',
                    icon: 'warning',
                    showCancelButton: true,
                    confirmButtonColor: '#dc3545',
                    cancelButtonColor: '#6c757d',
                    confirmButtonText: 'Sim, deixar vazio',
                    cancelButtonText: 'Restaurar Anterior'
                }).then((result) => {
                    if (result.isConfirmed) dispararFetch();
                    else cell.restoreOldValue();
                });
            } else {
                // Confirmação padrão para alterações normais
                Swal.fire({
                    title: 'Salvar Alteração?',
                    text: `Deseja realmente atualizar este campo?`,
                    icon: 'question',
                    showCancelButton: true,
                    confirmButtonColor: '#0d6efd',
                    cancelButtonColor: '#6c757d',
                    confirmButtonText: 'Salvar',
                    cancelButtonText: 'Cancelar'
                }).then((result) => {
                    if (result.isConfirmed) dispararFetch();
                    else cell.restoreOldValue(); // Restaura caso o usuário cancele
                });
            }
        },

        criarRNC: function (payload, btnSalvar, textoOriginalModal, formElement) {
            fetch(CONFIG.urls.criar, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': CONFIG.tokens.csrf},
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'sucesso') {
                    bootstrap.Modal.getInstance(document.getElementById('modalNovaRNC')).hide();
                    formElement.reset();
                    table.setData();
                } else {
                    Swal.fire('Erro!', JSON.stringify(data.mensagem), 'error');
                }
            })
            .catch(error => { Swal.fire('Erro!', 'Erro de conexão.', 'error'); })
            .finally(() => {
                btnSalvar.innerHTML = textoOriginalModal;
                btnSalvar.disabled = false;
            });
        },

        editarRNCAvancado: function (formData, rncId, btnSalvar, textoOriginal, formElement) {
            let url = CONFIG.urls.editarAvancadoBase + rncId + '/editar-avancado/';

            fetch(url, { method: 'POST', headers: { 'X-CSRFToken': CONFIG.tokens.csrf }, body: formData })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'sucesso') {
                    bootstrap.Modal.getInstance(document.getElementById('modalEditarRNC')).hide();
                    formElement.reset();
                    table.setData();
                    Swal.fire('Atualizado!', 'As alterações foram salvas com sucesso.', 'success');
                } else { Swal.fire("ERRO", JSON.stringify(data.mensagem), "error"); }
            })
            .catch(error => { Swal.fire("Erro de conexão", "", "error"); })
            .finally(() => {
                btnSalvar.innerHTML = textoOriginal;
                btnSalvar.disabled = false;
            });
        },

        deletarMidia: function(tipo, midiaId, rncId, btnElement) {
            Swal.fire({
                title: 'Excluir Evidência?',
                text: "Essa ação apagará o arquivo do servidor e não poderá ser desfeita!",
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#dc3545',
                cancelButtonColor: '#6c757d',
                confirmButtonText: '<i class="bi bi-trash"></i> Sim, excluir',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    btnElement.disabled = true;
                    let conteudoOriginal = btnElement.innerHTML;
                    btnElement.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

                    fetch(`/qualidade/api/rncs/midia/${tipo}/${midiaId}/deletar/`, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': CONFIG.tokens.csrf }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if(data.status === 'sucesso') {
                            let modalGaleria = bootstrap.Modal.getInstance(document.getElementById('modalGaleriaImagens'));
                            if(modalGaleria && tipo !== 'pdf') modalGaleria.hide();
                            table.setData();
                            Swal.fire('Excluído!', 'O arquivo foi removido com sucesso.', 'success');
                        } else {
                            Swal.fire('Erro!', data.mensagem, 'error');
                            btnElement.disabled = false;
                            btnElement.innerHTML = conteudoOriginal;
                        }
                    }).catch(error => {
                        Swal.fire('Erro!', 'Falha de comunicação com o servidor.', 'error');
                        btnElement.disabled = false;
                        btnElement.innerHTML = conteudoOriginal;
                    });
                }
            });
        }
    };

    // INTERFACE DE USUÁRIO (Modais)
    const ui = {
        abrirModalEdicao: function(dados) {
            document.getElementById('display_rnc_id').innerText = dados.id;
            document.getElementById('edit_rnc_id').value = dados.id;
            document.getElementById('edit_registrador_id').value = dados.registrador_id || "";

            let ehBloqueado = !CONFIG.isSGQ;
            if(document.getElementById('edit_status')) { document.getElementById('edit_status').value = dados.status_code || ''; document.getElementById('edit_status').disabled = ehBloqueado; }
            if(document.getElementById('edit_categoria')) { document.getElementById('edit_categoria').value = dados.categoria_code || ''; document.getElementById('edit_categoria').disabled = ehBloqueado; }
            if(document.getElementById('edit_origem')) { document.getElementById('edit_origem').value = dados.origem_code || ''; document.getElementById('edit_origem').disabled = ehBloqueado; }
            if(document.getElementById('edit_criticidade')) { document.getElementById('edit_criticidade').value = dados.criticidade_code || ''; document.getElementById('edit_criticidade').disabled = ehBloqueado; }
            if(document.getElementById('edit_detector')) { document.getElementById('edit_detector').value = dados.detector_code || ''; document.getElementById('edit_detector').disabled = ehBloqueado; }
            if(document.getElementById('edit_local_id')) { document.getElementById('edit_local_id').value = dados.local_id || ''; document.getElementById('edit_local_id').disabled = ehBloqueado; }
            if(document.getElementById('edit_equipamento_id')) { document.getElementById('edit_equipamento_id').value = dados.equipamento_id || ''; document.getElementById('edit_equipamento_id').disabled = ehBloqueado; }

            if(document.getElementById('edit_data_encerramento')) { document.getElementById('edit_data_encerramento').value = dados.data_encerramento ? dados.data_encerramento.replaceAll('/', '-') : ''; document.getElementById('edit_data_encerramento').readOnly = ehBloqueado; }
            if(document.getElementById('edit_data_prevista')) { document.getElementById('edit_data_prevista').value = dados.data_prevista_conclusao ? dados.data_prevista_conclusao.replaceAll('/', '-') : ''; document.getElementById('edit_data_prevista').readOnly = ehBloqueado; }
            if(document.getElementById('edit_ishikawa_link')) document.getElementById('edit_ishikawa_link').value = dados.ishikawa_link || '';

            let idsResponsaveis = dados.responsaveis_ids || [];
            if (choicesResp) {
                choicesResp.removeActiveItems();
                if (idsResponsaveis.length > 0) choicesResp.setChoiceByValue(idsResponsaveis.map(String));
            }

            new bootstrap.Modal(document.getElementById('modalEditarRNC')).show();
        },

        abrirGaleriaImagens: function(dados, tipo) {
            let containerGaleria = document.getElementById('galeria_content');
            containerGaleria.innerHTML = '';

            let imagensArray = []
            let tituloModal = document.querySelector('#modalGaleriaImagens .modal-title');

            if (tipo === TIPO_GALERIA.EFICACIA) {
                imagensArray = dados.eficacia_imagens_dados || [];
                tituloModal.innerHTML = '<i class="bi bi-shield-check me-2"></i>Evidências de Eficácia';
            } else if (tipo === TIPO_GALERIA.NC){
                imagensArray = dados.imagens_dados || [];
                tituloModal.innerHTML = '<i class="bi bi-images me-2"></i>Evidências Fotográficas da Falha';
            }
            else {
                console.error('Tipo galeria não cadastrado');
                return;
            }

            imagensArray.forEach(imgObj => {
                containerGaleria.innerHTML += `
                    <div class="col-md-4 position-relative">
                        <button type="button" 
                                class="btn btn-danger btn-sm position-absolute top-0 end-0 m-2 shadow" 
                                title="Excluir Evidência"
                                onclick="RNCDashboard.api.deletarMidia('${tipo}', ${imgObj.id}, ${dados.id}, this)">
                            <i class="bi bi-trash"></i>
                        </button>
                        
                        <a href="${imgObj.url}" target="_blank">
                            <img src="${imgObj.url}" class="img-fluid img-thumbnail shadow-sm rounded-2" style="max-height: 200px; width: 100%; object-fit: cover;">
                        </a>
                    </div>`;
            });
            new bootstrap.Modal(document.getElementById('modalGaleriaImagens')).show();
        }
    };

    // INICIALIZADOR PÚBLICO
    return {
        init: function() {
            if(!CONFIG) {
                console.error("Configurações não encontradas.");
                return;
            }
            initChoices();
            initTabulator();

            let btnExportar = document.getElementById("download-xlsx");
            if(btnExportar) btnExportar.addEventListener("click", () => table.download("xlsx", "Controle_RNCs.xlsx", {sheetName:"RNCs"}));

            let formNovaRNC = document.getElementById("formNovaRNC");
            if (formNovaRNC) {
                formNovaRNC.addEventListener("submit", function(event) {
                    event.preventDefault();
                    let formData = new FormData(this);
                    let payload = Object.fromEntries(formData.entries());
                    payload['responsaveis'] = formData.getAll('responsaveis');

                    let btnSalvar = document.getElementById("btnSalvarNovaRNC");
                    let textoOriginal = btnSalvar.innerHTML;
                    btnSalvar.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Salvando...';
                    btnSalvar.disabled = true;

                    api.criarRNC(payload, btnSalvar, textoOriginal, this);
                });
            }

            let formEditar = document.getElementById("formEditarRNC");
            if (formEditar) {
                formEditar.addEventListener("submit", function(event) {
                    event.preventDefault();
                    let formData = new FormData(this);
                    let rncId = document.getElementById('edit_rnc_id').value;

                    let btnSalvar = document.getElementById("btnSalvarEdicaoRNC");
                    let textoOriginal = btnSalvar.innerHTML;
                    btnSalvar.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Salvando...';
                    btnSalvar.disabled = true;

                    api.editarRNCAvancado(formData, rncId, btnSalvar, textoOriginal, this);
                });
            }
        },
        api: api
    };
})();

document.addEventListener('DOMContentLoaded', RNCDashboard.init);