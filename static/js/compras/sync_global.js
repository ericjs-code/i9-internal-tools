document.addEventListener('DOMContentLoaded', function() {
    // 1. Busca TODOS os botões que tenham a classe global
    const botoesSync = document.querySelectorAll('.btn-sync-global');

    // 2. Itera sobre cada botão encontrado e acopla o listener
    botoesSync.forEach(btn => {
        btn.addEventListener('click', function(event) {
            // Previne comportamento padrão
            event.preventDefault();

            const btnAtual = event.currentTarget;
            const urlSync = btnAtual.getAttribute('data-url');
            const csrfToken = btnAtual.getAttribute('data-csrf');

            Swal.fire({
                title: 'Sincronizar com Protheus?',
                text: "Isso atualizará a base de dados com as informações mais recentes do ERP.",
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#0d6efd',
                confirmButtonText: 'Sim, atualizar!',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
                if (result.isConfirmed) {
                    iniciarSincronizacao(urlSync, csrfToken);
                }
            });
        });
    });
});

function iniciarSincronizacao(urlSync, csrfToken) {
    Swal.fire({
        title: 'Sincronizando...',
        html: 'O sistema está processando os dados do Protheus. <b></b>',
        timerProgressBar: true,
        allowOutsideClick: false, // UX: Impede fechamento acidental
        didOpen: () => {
            Swal.showLoading();

            fetch(urlSync, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'processing') {
                    monitorarStatus(data.task_id);
                } else if (data.status === 'locked') {
                    Swal.fire('Aviso', data.message, 'warning');
                } else {
                    Swal.fire('Aviso', data.message, 'info');
                }
            })
            .catch(error => {
                console.error("Erro no Fetch:", error);
                Swal.fire('Erro', 'Falha na comunicação com o servidor.', 'error');
            });
        }
    });
}

function monitorarStatus(taskId) {
    // Usamos setTimeout recursivo em vez de setInterval
    const checkStatus = () => {
        fetch(`/compras/checar-status-sync/${taskId}/`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'SUCCESS') {
                    Swal.fire({
                        title: 'Sucesso!',
                        text: 'Dados atualizados.',
                        icon: 'success'
                    }).then(() => location.reload());
                } else if (data.status === 'FAILURE') {
                    Swal.fire('Erro', 'O processamento falhou no servidor.', 'error');
                } else {
                    // Tenta novamente em 3 segundos, apenas se o processo ainda estiver vivo
                    setTimeout(checkStatus, 3000);
                }
            })
            .catch(error => {
                console.error("Erro no Polling:", error);
                // Em caso de erro de rede, podemos parar ou tentar poucas vezes
            });
    };
    // Inicia a primeira chamada
    checkStatus();
}