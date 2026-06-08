from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def group_required(group_names):
    """
    [NOVO] Decorador moderno para verificação de acesso via Django Groups (RBAC).
    
    Aceita uma lista de nomes de grupos. O usuário precisa pertencer a 
    pelo menos um deles, ou ter perfis de acesso global (TI, Diretoria, Superuser).
    
    Ex: @group_required(['Engenharia', 'Qualidade'])
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Otimização: Avaliamos os grupos em memória
            user_groups = [group.name for group in request.user.groups.all()]
            
            # Regra de negócio: TI e Diretoria têm acesso irrestrito
            # (No futuro, se isolarmos as permissões totalmente, removeremos essa checagem daqui)
            if 'Diretoria' in user_groups or 'TI' in user_groups:
                return view_func(request, *args, **kwargs)
                
            # Verifica interseção: O usuário tem pelo menos um dos grupos requisitados?
            if any(group in user_groups for group in group_names):
                return view_func(request, *args, **kwargs)

            messages.error(request, 'Você não possui os privilégios necessários para acessar este módulo. Por favor, contate o administrador do sistema.')
            return redirect('home')
        return _wrapped_view
    return decorator


def exige_permissao(modulos_aceitos):
    mapa_grupos = {
        'rh': 'RH',
        'ti': 'TI',
        'comercial': 'Comercial',
        'compras': 'Compras',
        'engenharia': 'Engenharia',
        'qualidade': 'Qualidade',
        'rdo': 'RDO',
    }
    grupos = [mapa_grupos.get(modulo, modulo) for modulo in modulos_aceitos]
    return group_required(grupos)
