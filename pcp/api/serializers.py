from __future__ import annotations

from rest_framework import serializers

from pcp.models import (
    CriticidadeAtivo,
    PcpAreaProducao,
    PcpAtivo,
    PcpDowntime,
    PcpExecucaoManutencao,
    PcpPlanoManutencao,
    PcpProgramacaoManutencao,
    StatusAtivo,
    TipoDowntime,
    TipoManutencao,
)


class AreaProducaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PcpAreaProducao
        fields = ["id", "codigo", "nome", "descricao", "ativo", "created_at", "updated_at"]
        read_only_fields = ["id", "ativo", "created_at", "updated_at"]


class AtivoSerializer(serializers.ModelSerializer):
    area_codigo = serializers.CharField(source="area.codigo", read_only=True)
    area_nome = serializers.CharField(source="area.nome", read_only=True)

    class Meta:
        model = PcpAtivo
        fields = [
            "id",
            "codigo",
            "nome",
            "descricao",
            "fabricante",
            "modelo",
            "numero_serie",
            "area",
            "area_codigo",
            "area_nome",
            "status",
            "criticidade",
            "ativo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "area_codigo", "area_nome", "ativo", "created_at", "updated_at"]


class AtivoCreateSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=50)
    nome = serializers.CharField(max_length=150)
    descricao = serializers.CharField(required=False, allow_blank=True)
    fabricante = serializers.CharField(required=False, allow_blank=True, max_length=120)
    modelo = serializers.CharField(required=False, allow_blank=True, max_length=120)
    numero_serie = serializers.CharField(required=False, allow_blank=True, max_length=120)
    status = serializers.ChoiceField(choices=StatusAtivo.choices, required=False)
    criticidade = serializers.ChoiceField(choices=CriticidadeAtivo.choices, required=False)


class PlanoManutencaoSerializer(serializers.ModelSerializer):
    ativo_codigo = serializers.CharField(source="ativo_pcp.codigo", read_only=True)

    class Meta:
        model = PcpPlanoManutencao
        fields = [
            "id",
            "ativo_pcp",
            "ativo_codigo",
            "tipo",
            "nome",
            "descricao",
            "intervalo_dias",
            "data_inicio",
            "ativo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "ativo_codigo", "ativo", "created_at", "updated_at"]


class PlanoManutencaoCreateSerializer(serializers.Serializer):
    ativo_pcp = serializers.PrimaryKeyRelatedField(queryset=PcpAtivo.objects.all())
    nome = serializers.CharField(max_length=150)
    data_inicio = serializers.DateField()
    tipo = serializers.ChoiceField(choices=TipoManutencao.choices, required=False)
    descricao = serializers.CharField(required=False, allow_blank=True)
    intervalo_dias = serializers.IntegerField(min_value=1)


class ProgramacaoManutencaoSerializer(serializers.ModelSerializer):
    ativo_pcp = serializers.IntegerField(source="plano.ativo_pcp_id", read_only=True)
    ativo_codigo = serializers.CharField(source="plano.ativo_pcp.codigo", read_only=True)
    plano_nome = serializers.CharField(source="plano.nome", read_only=True)

    class Meta:
        model = PcpProgramacaoManutencao
        fields = [
            "id",
            "plano",
            "plano_nome",
            "ativo_pcp",
            "ativo_codigo",
            "data_prevista",
            "data_limite",
            "status",
            "origem",
            "ativo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RecalcularPreventivasSerializer(serializers.Serializer):
    referencia = serializers.DateField(required=False)


class DowntimeSerializer(serializers.ModelSerializer):
    ativo_codigo = serializers.CharField(source="ativo_pcp.codigo", read_only=True)
    ativo_nome = serializers.CharField(source="ativo_pcp.nome", read_only=True)
    categoria_descricao = serializers.CharField(source="get_categoria_display", read_only=True)
    tipo_descricao = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = PcpDowntime
        fields = [
            "id",
            "ativo_pcp",
            "ativo_codigo",
            "ativo_nome",
            "categoria",
            "categoria_descricao",
            "tipo",
            "tipo_descricao",
            "inicio",
            "fim",
            "duracao_minutos",
            "motivo",
            "observacao",
            "origem",
            "responsavel",
            "ativo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "ativo_codigo",
            "ativo_nome",
            "categoria",
            "categoria_descricao",
            "tipo_descricao",
            "duracao_minutos",
            "responsavel",
            "ativo",
            "created_at",
            "updated_at",
        ]


class DowntimeOpenSerializer(serializers.Serializer):
    ativo_pcp = serializers.PrimaryKeyRelatedField(queryset=PcpAtivo.objects.all())
    motivo = serializers.CharField(max_length=255)
    tipo = serializers.ChoiceField(choices=TipoDowntime.choices, required=False)
    inicio = serializers.DateTimeField(required=False)
    observacao = serializers.CharField(required=False, allow_blank=True)


class DowntimeCloseSerializer(serializers.Serializer):
    fim = serializers.DateTimeField(required=False)
    observacao = serializers.CharField(required=False, allow_blank=True)


class ExecucaoManutencaoSerializer(serializers.ModelSerializer):
    ativo_codigo = serializers.CharField(source="ativo_pcp.codigo", read_only=True)
    plano_nome = serializers.CharField(source="programacao.plano.nome", read_only=True)

    class Meta:
        model = PcpExecucaoManutencao
        fields = [
            "id",
            "protocolo",
            "programacao",
            "plano_nome",
            "ativo_pcp",
            "ativo_codigo",
            "tipo",
            "data_inicio",
            "data_fim",
            "observacao",
            "diagnostico",
            "servicos_executados",
            "resultado",
            "recomendacoes",
            "concluido_em",
            "concluido_por",
            "responsavel",
            "ativo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ExecucaoManutencaoStartSerializer(serializers.Serializer):
    ativo_pcp = serializers.PrimaryKeyRelatedField(queryset=PcpAtivo.objects.all())
    programacao = serializers.PrimaryKeyRelatedField(
        queryset=PcpProgramacaoManutencao.objects.all(),
        required=False,
        allow_null=True,
    )
    tipo = serializers.ChoiceField(choices=TipoManutencao.choices)
    data_inicio = serializers.DateTimeField(required=False)
    observacao = serializers.CharField(required=False, allow_blank=True)


class ExecucaoManutencaoCloseSerializer(serializers.Serializer):
    data_fim = serializers.DateTimeField(required=False)
    diagnostico = serializers.CharField(required=False, allow_blank=True)
    servicos_executados = serializers.CharField(required=False, allow_blank=True)
    resultado = serializers.CharField(required=False, allow_blank=True)
    recomendacoes = serializers.CharField(required=False, allow_blank=True)
