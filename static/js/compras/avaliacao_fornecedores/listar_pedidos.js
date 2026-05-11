document.getElementById('btnSync').addEventListener('click', function(event) {
    // 1. Captura as variáveis do Django escondidas no botão
    const btn = event.currentTarget;
    const urlSync = btn.getAttribute('data-url');
    const csrfToken = btn.getAttribute('data-csrf');

    Swal.fire({
        title: 'Sincronizar com Protheus?',
        text: "Isso atualizará a base de pedidos entregues.",
        icon: 'question',
        showCancelButton: true,
        confirmButtonText: 'Sim, atualizar!',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) {
            iniciarSincronizacao(urlSync, csrfToken); // 2. Passa para a função
        }
    });
});

function iniciarSincronizacao(urlSync, csrfToken) {
    Swal.fire({
        title: 'Sincronizando...',
        html: 'O sistema está processando os dados do Protheus. <b></b>',
        timerProgressBar: true,
        didOpen: () => {
            Swal.showLoading();

            // 3. Usa as variáveis dinâmicas capturadas
            fetch(urlSync, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'processing') {
                    monitorarStatus(data.task_id);
                } else {
                    Swal.fire('Aviso', data.message, 'info');
                }
            })
            .catch(error => {
                console.error(error);
                Swal.fire('Erro', 'Falha na comunicação.', 'error');
            });
        }
    });
}

function monitorarStatus(taskId) {
    const checkInterval = setInterval(() => {
        // A rota abaixo não exige tag do Django pois estamos concatenando uma string fixa com o ID
        fetch(`/compras/checar-status-sync/${taskId}/`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'SUCCESS') {
                    clearInterval(checkInterval);
                    Swal.fire({
                        title: 'Sucesso!',
                        text: 'Dados atualizados. A página será recarregada.',
                        icon: 'success'
                    }).then(() => location.reload());
                } else if (data.status === 'FAILURE') {
                    clearInterval(checkInterval);
                    Swal.fire('Erro', 'Ocorreu uma falha no ETL.', 'error');
                }
            })
            .catch(error => console.error("Erro ao checar status:", error));
    }, 2000);
}