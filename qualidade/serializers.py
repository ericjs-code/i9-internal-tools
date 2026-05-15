from rest_framework import serializers
from . models import RNC

class RNCSerializer(serializers.ModelSerializer):
    class Meta:
        model = RNC
        fields = [
            'projeto_cod',
            'elemento_rastreador',
            'detector',
            'categoria',
            'origem',
            'criticidade',
            'status',
            'equipamento',
            'local',
            'descricao',
            'correcao',
            'ishikawa_link',
            'causas_principais',
            'acao_corretiva',
            'eficacia_texto',
            'responsaveis',
            'data_encerramento',
            'data_prevista_conclusao',
            'versao',
            'registrador'
        ]