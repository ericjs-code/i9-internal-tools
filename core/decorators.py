from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def exige_permissao(modulos_aceitos):
    """Decorador para exige acesso"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            for modulo in modulos_aceitos:
                if request.user.pode_acessar_modulo(modulo):
                    return view_func(request, *args, **kwargs)

            messages.error (request, 'Você não possui os privilégios necessários para acessar este módulo. Por favor, contate o administrador do sistema.')
            return redirect('home')
        return _wrapped_view
    return decorator
