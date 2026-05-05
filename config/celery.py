import os
from celery import Celery

# Define o módulo de configurações padrão do Django para o Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Instancia o aplicativo Celery
app = Celery('sistema_i9')

# Lê as configurações do Django que começam com 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Procura automaticamente por arquivos tasks.py dentro de todos os seus apps (compras, rh, etc)
app.autodiscover_tasks()