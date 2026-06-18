from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    """
    Configuração para exibir e gerenciar o CustomUser no Django Admin.
    
    Herda todas as funcionalidades do UserAdmin padrão (gestão de senha,
    permissões, grupos, etc.) e apenas adapta para o nosso modelo.
    """
    model = CustomUser
    
    # Mantém os fieldsets padrão, mas você pode customizá-los se necessário.
    # Por exemplo, se você tivesse campos extras no CustomUser, adicionaria aqui.
    fieldsets = UserAdmin.fieldsets + (
        ('Campos Customizados', {'fields': ('teams_username', 'must_change_password')}),
    )
    
    # Adiciona os campos customizados na lista de exibição principal.
    list_display = ('username', 'email', 'first_name', 'last_name', 'must_change_password', 'is_staff')

# Registra o nosso modelo CustomUser com a configuração customizada do Admin.
admin.site.register(CustomUser, CustomUserAdmin)
