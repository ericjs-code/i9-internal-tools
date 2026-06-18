from django.shortcuts import redirect, render
from celery.result import AsyncResult
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


SENHA_PADRAO_IMPORTACAO_AVALIACAO = 'tmg@2026'

@login_required(login_url='/login/')
def home(request):
    return render(request, 'home.html')


@login_required(login_url='/login/')
def checar_status_task_global(request, task_id):
    """
    View global e genérica para consultar o status de QUALQUER
    task do Celery rodando em background no sistema.
    """
    task_result = AsyncResult(task_id)
    return JsonResponse({
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None
    })


@login_required(login_url='/login/')
def trocar_senha_obrigatoria(request):
    if not getattr(request.user, 'must_change_password', False):
        return redirect('home')

    if request.method == 'POST':
        nova_senha = request.POST.get('nova_senha') or ''
        confirmar_senha = request.POST.get('confirmar_senha') or ''

        if nova_senha != confirmar_senha:
            messages.error(request, 'A nova senha e a confirmacao precisam ser iguais.')
        elif nova_senha == SENHA_PADRAO_IMPORTACAO_AVALIACAO:
            messages.error(request, 'A nova senha nao pode ser igual a senha padrao inicial.')
        elif request.user.check_password(nova_senha):
            messages.error(request, 'A nova senha nao pode ser igual a senha atual.')
        else:
            try:
                validate_password(nova_senha, user=request.user)
            except ValidationError as exc:
                for erro in exc.messages:
                    messages.error(request, erro)
            else:
                request.user.set_password(nova_senha)
                request.user.must_change_password = False
                request.user.save(update_fields=['password', 'must_change_password'])
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Senha alterada com sucesso.')
                return redirect('home')

    return render(request, 'core/auth/trocar_senha_obrigatoria.html')
