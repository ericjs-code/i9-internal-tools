"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static
from core.views import home
from django.contrib.auth import views as auth_views

urlpatterns = [
            path('painel-i9tmg-restrito/', admin.site.urls),
            path('login/', auth_views.LoginView.as_view(
                template_name='core/login.html',
                redirect_authenticated_user=True
            ), name='login'),
            path('logout/', auth_views.LogoutView.as_view(), name='logout'),
            path('senha/redefinir/', auth_views.PasswordResetView.as_view(
                template_name='core/auth/password_reset_form.html',
                email_template_name='core/auth/password_reset_email.txt',
                subject_template_name='core/auth/password_reset_subject.txt',
                success_url=reverse_lazy('password_reset_done'),
            ), name='password_reset'),
            path('senha/redefinir/enviado/', auth_views.PasswordResetDoneView.as_view(
                template_name='core/auth/password_reset_done.html',
            ), name='password_reset_done'),
            path('senha/redefinir/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
                template_name='core/auth/password_reset_confirm.html',
                success_url=reverse_lazy('password_reset_complete'),
            ), name='password_reset_confirm'),
            path('senha/redefinir/concluido/', auth_views.PasswordResetCompleteView.as_view(
                template_name='core/auth/password_reset_complete.html',
            ), name='password_reset_complete'),
            path('', home, name='home'),
            path('comercial/', include('comercial.urls')),
            path('ti/', include('ti.urls')),
            path('rh/', include('rh.urls')),
            path('compras/', include('compras.urls')),
            path('qualidade/', include('qualidade.urls')),
            path('engenharia/', include('engenharia.urls')),
            path('reserva_sala/', include('reserva_sala.urls')),
            path('core/', include('core.urls')),
            path('rdo/', include('rdo.urls')),
            
            # API endpoints
            path('api/pcp/', include('pcp.api.urls')),

        ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
