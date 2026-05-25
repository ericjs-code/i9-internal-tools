document.addEventListener('DOMContentLoaded', function() {
    const botoesSync = document.querySelectorAll('.btn-sync-global');

    botoesSync.forEach(btn => {
        btn.addEventListener('click', function(event) {
            event.preventDefault(); // Impede forms perdidos de recarregarem a página

            const btnAtual = event.currentTarget;
            const urlSync = btnAtual.getAttribute('data-url');
            const urlCheckBase = btnAtual.getAttribute('data-check-url');
            const csrfToken = btnAtual.getAttribute('data-csrf');

            Swal.fire({
                title: 'Iniciar Sincronização?',
                text: "O sistema buscará as informações mais recentes do servidor.",
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#0d6efd',
                confirmButtonText: 'Sim, sincronizar',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    iniciarProcessamentoGlobal(urlSync, urlCheckBase, csrfToken);
                }
            });
        });
    });
});

function iniciarProcessamentoGlobal(urlSync, urlCheckBase, csrfToken) {
    Swal.fire({
        title: 'Sincronizando...',
        html: 'O processamento em background foi iniciado. Por favor, aguarde... <b></b>',
        timerProgressBar: true,
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();

            fetch(urlSync, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'processing') {
                    // Substitui o placeholder da URL pelo ID real da Task que o Celery retornou
                    const urlCheckFinal = urlCheckBase.replace('TASK_ID_PLACEHOLDER', data.task_id);
                    monitorarStatusGlobal(urlCheckFinal);
                } else if (data.status === 'locked') {
                    Swal.fire('Sincronização em Andamento', data.message, 'warning');
                } else {
                    Swal.fire('Aviso', data.message, 'info');
                }
            })
            .catch(error => {
                console.error("Erro no Fetch:", error);
                Swal.fire('Erro Crítico', 'Falha ao conectar com o servidor.', 'error');
            });
        }
    });
}

function monitorarStatusGlobal(urlCheck) {
    const checkStatus = () => {
        fetch(urlCheck)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'SUCCESS') {
                    Swal.fire({
                        title: 'Concluído!',
                        text: 'Dados atualizados com sucesso.',
                        icon: 'success'
                    }).then(() => location.reload());
                } else if (data.status === 'FAILURE') {
                    Swal.fire('Falha no Servidor', 'Ocorreu um erro no processamento do Celery.', 'error');
                } else {
                    // PENDENTE / STARTED -> Polling de 3 segundos
                    setTimeout(checkStatus, 3000);
                }
            })
            .catch(error => {
                console.error("Erro no Polling:", error);
            });
    };
    checkStatus();
}