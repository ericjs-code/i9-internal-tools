function mostrarCarregamento(form) {
    event.preventDefault();

    const botao = form.querySelector("button");
    const texto = form.querySelector("#texto-sync");

    texto.innerText = "Iniciando...";
    botao.disabled = true;

    // Dispara a View via AJAX
    fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: {'X-Requested-With': 'XMLHttpRequest'}
    })
    .then(response => response.json())
    .then(data => {
        if(data.status === 'locked') {
            alert(data.message);
            botao.disabled = false;
            texto.innerText = "Sincronizar com Protheus";
        } else if (data.status === 'processing') {
            texto.innerText = "Sincronizando (pode levar minutos)...";
            // Inicia o Polling chamando a nova URL
            iniciarPolling(data.task_id);
        }
    });
}

function iniciarPolling(taskId) {
    const intervalo = setInterval(() => {
        fetch(`/compras/checar-status-sync/${taskId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                clearInterval(intervalo);
                window.location.reload();
            } else if (data.status === 'FAILURE') {
                clearInterval(intervalo);
                alert("Falha no ETL.");
                window.location.reload();
            }
        });
    }, 3000); // Pergunta a cada 3 segundos
}