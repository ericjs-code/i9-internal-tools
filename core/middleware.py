from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, resolve


ROTAS_PERMITIDAS_TROCA_SENHA = {
    'logout',
    'login',
    'trocar_senha_obrigatoria',
    'password_reset',
    'password_reset_done',
    'password_reset_confirm',
    'password_reset_complete',
}


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._deve_redirecionar(request):
            return redirect('trocar_senha_obrigatoria')
        return self.get_response(request)

    def _deve_redirecionar(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        if not getattr(user, 'must_change_password', False):
            return False

        if self._caminho_estatico_ou_media(request.path):
            return False

        try:
            match = resolve(request.path_info)
        except Resolver404:
            return False

        return match.url_name not in ROTAS_PERMITIDAS_TROCA_SENHA

    def _caminho_estatico_ou_media(self, path):
        prefixos = [settings.STATIC_URL, settings.MEDIA_URL]
        return any(prefixo and path.startswith(prefixo) for prefixo in prefixos)
