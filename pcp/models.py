from __future__ import annotations

import uuid
from pathlib import Path
from typing import TypeVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from pcp.storage import PcpPrivateStorage


TSoftDeleteModel = TypeVar("TSoftDeleteModel", bound="SoftDeleteModel")


class SoftDeleteQuerySet(models.QuerySet[TSoftDeleteModel]):
    def delete(self) -> tuple[int, dict[str, int]]:
        updated = self.update(ativo=False, updated_at=timezone.now())
        return updated, {self.model._meta.label: updated}

    def active(self) -> "SoftDeleteQuerySet[TSoftDeleteModel]":
        return self.filter(ativo=True)


class ActiveManager(models.Manager[TSoftDeleteModel]):
    def get_queryset(self) -> SoftDeleteQuerySet[TSoftDeleteModel]:
        return SoftDeleteQuerySet(self.model, using=self._db).filter(ativo=True)


class AllObjectsManager(models.Manager[TSoftDeleteModel]):
    def get_queryset(self) -> SoftDeleteQuerySet[TSoftDeleteModel]:
        return SoftDeleteQuerySet(self.model, using=self._db)


class ImmutableAuditQuerySet(models.QuerySet["PcpEventoAuditoriaManutencao"]):
    def delete(self) -> None:
        raise ValueError("Eventos de auditoria não podem ser excluídos.")

    def update(self, **kwargs: object) -> None:
        raise ValueError("Eventos de auditoria não podem ser alterados.")


class ImmutableAuditManager(models.Manager["PcpEventoAuditoriaManutencao"]):
    def get_queryset(self) -> ImmutableAuditQuerySet:
        return ImmutableAuditQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    ativo = models.BooleanField(default=True, db_index=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using: str | None = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        self.ativo = False
        self.save(using=using, update_fields=["ativo", "updated_at"])
        return 1, {self._meta.label: 1}


class TipoMovimentacao(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saída"


class OrigemMovimentacao(models.TextChoices):
    NF_ENTRADA = "NF_ENTRADA", "Nota Fiscal de Entrada"
    NF_SAIDA = "NF_SAIDA", "Nota Fiscal de Saída"
    MOV_INTERNA = "MOV_INTERNA", "Movimentação Interna"


class StatusAtivo(models.TextChoices):
    OPERANDO = "operando", "Operando"
    PARADO = "parado", "Parado"
    MANUTENCAO = "manutencao", "Em manutenção"
    INATIVO = "inativo", "Inativo"


class CriticidadeAtivo(models.TextChoices):
    BAIXA = "baixa", "Baixa"
    MEDIA = "media", "Média"
    ALTA = "alta", "Alta"
    CRITICA = "critica", "Crítica"


class TipoManutencao(models.TextChoices):
    PREVENTIVA = "preventiva", "Preventiva"
    CORRETIVA = "corretiva", "Corretiva"
    PREDITIVA = "preditiva", "Preditiva"
    INSPECAO = "inspecao", "Inspeção"


class StatusManutencao(models.TextChoices):
    PLANEJADA = "planejada", "Planejada"
    EM_EXECUCAO = "em_execucao", "Em execução"
    CONCLUIDA = "concluida", "Concluída"
    CANCELADA = "cancelada", "Cancelada"


class CategoriaDowntime(models.TextChoices):
    TEMPO_PRODUCAO_PERDIDO = "tempo_producao_perdido", "Tempo de Produção (Perdido)"
    TEMPO_OCIOSO = "tempo_ocioso", "Tempo Ocioso"


class TipoDowntime(models.TextChoices):
    FALTA_MAO_OBRA = "falta_mao_obra", "Falta de mão de obra"
    MAQUINARIO_ESTRAGOU = "maquinario_estragou", "Maquinário estragou"
    FALTA_MATERIAL = "falta_material", "Falta de material"
    MANUTENCAO = "manutencao", "Manutenção"
    FALTA_DESENHO = "falta_desenho", "Falta de desenho"


TIPOS_DOWNTIME_TEMPO_PRODUCAO = (
    TipoDowntime.FALTA_MAO_OBRA,
    TipoDowntime.MAQUINARIO_ESTRAGOU,
    TipoDowntime.FALTA_MATERIAL,
    TipoDowntime.MANUTENCAO,
)
TIPOS_DOWNTIME_TEMPO_OCIOSO = (TipoDowntime.FALTA_DESENHO,)
TIPOS_DOWNTIME_LEGADOS = ("nao_planejado", "planejado", "setup", "qualidade")
CATEGORIA_POR_TIPO_DOWNTIME: dict[str, str] = {
    **{tipo: CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO for tipo in TIPOS_DOWNTIME_TEMPO_PRODUCAO},
    **{tipo: CategoriaDowntime.TEMPO_OCIOSO for tipo in TIPOS_DOWNTIME_TEMPO_OCIOSO},
    **{tipo: CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO for tipo in TIPOS_DOWNTIME_LEGADOS},
}


class OrigemApontamento(models.TextChoices):
    MANUAL = "manual", "Manual"
    CELERY = "celery", "Celery"
    ETL = "etl", "ETL"
    SISTEMA = "sistema", "Sistema"


class TipoAlerta(models.TextChoices):
    PREVENTIVA = "preventiva", "Preventiva"
    DOWNTIME_ABERTO = "downtime_aberto", "Downtime aberto"


class StatusAlerta(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    ENVIANDO = "enviando", "Enviando"
    ENVIADO = "enviado", "Enviado"
    FALHA = "falha", "Falha"
    CANCELADO = "cancelado", "Cancelado"


class TipoEventoAuditoria(models.TextChoices):
    CRIADA = "criada", "Manutenção criada"
    INICIADA = "iniciada", "Manutenção iniciada"
    CONCLUIDA = "concluida", "Manutenção concluída"
    CORRIGIDA = "corrigida", "Correção documental"
    EVIDENCIA_ADICIONADA = "evidencia_adicionada", "Evidência adicionada"
    EVIDENCIA_DESATIVADA = "evidencia_desativada", "Evidência desativada"


class TipoEvidencia(models.TextChoices):
    PDF = "pdf", "PDF"
    IMAGEM = "imagem", "Imagem"


class FinalidadeEvidencia(models.TextChoices):
    PROBLEMA = "problema", "Evidência do problema"
    SOLUCAO_DOCUMENTACAO = "solucao_documentacao", "Evidência da solução / documentação"


MARCOS_ALERTA_PREVENTIVA = (30, 15, 7, 1)
pcp_private_storage = PcpPrivateStorage()


def evidencia_manutencao_upload_to(instance: "PcpEvidenciaManutencao", filename: str) -> str:
    extensao = Path(filename).suffix.lower()
    return f"manutencoes/{instance.execucao.protocolo}/{uuid.uuid4().hex}{extensao}"


class MovimentacaoEstoquePCP(SoftDeleteModel):
    filial = models.CharField(max_length=10, default="", db_index=True, verbose_name="Filial")
    produto_codigo = models.CharField(max_length=50, db_index=True, verbose_name="Código do Produto")
    data_movimentacao = models.DateField(db_index=True, verbose_name="Data da Movimentação")
    tipo_movimentacao = models.CharField(
        max_length=10,
        choices=TipoMovimentacao.choices,
        db_index=True,
        verbose_name="Tipo de Movimentação",
    )
    origem_movimentacao = models.CharField(
        max_length=20,
        choices=OrigemMovimentacao.choices,
        db_index=True,
        verbose_name="Origem da Movimentação",
    )
    quantidade = models.DecimalField(max_digits=19, decimal_places=5, verbose_name="Quantidade")
    documento = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Documento de Origem",
    )
    cf_operacao = models.CharField(
        max_length=5,
        blank=True,
        default="",
        verbose_name="CF da Operação (SD3)",
    )

    class Meta:
        verbose_name = "Movimentação de Estoque (PCP)"
        verbose_name_plural = "Movimentações de Estoque (PCP)"
        db_table = "pcp_movimentacaoestoquepcp"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "filial",
                    "produto_codigo",
                    "data_movimentacao",
                    "tipo_movimentacao",
                    "origem_movimentacao",
                    "documento",
                    "cf_operacao",
                ],
                name="pcp_movimentacao_natural_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(quantidade__gte=0),
                name="pcp_movimentacao_quantidade_gte_zero",
            ),
        ]
        indexes = [
            models.Index(fields=["filial", "produto_codigo", "data_movimentacao"], name="pcp_mov_fil_prod_data_idx"),
            models.Index(fields=["ativo", "data_movimentacao"], name="pcp_mov_ativo_data_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.produto_codigo} - {self.data_movimentacao}"


class PcpAreaProducao(SoftDeleteModel):
    codigo = models.CharField(max_length=30, unique=True, db_index=True, verbose_name="Código")
    nome = models.CharField(max_length=120, db_index=True, verbose_name="Nome")
    descricao = models.TextField(blank=True, verbose_name="Descrição")

    class Meta:
        verbose_name = "Área de Produção"
        verbose_name_plural = "Áreas de Produção"
        db_table = "pcp_area_producao"

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nome}"


class PcpAtivo(SoftDeleteModel):
    codigo = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Código")
    nome = models.CharField(max_length=150, db_index=True, verbose_name="Nome")
    descricao = models.TextField(blank=True, verbose_name="Descrição")
    fabricante = models.CharField(max_length=120, blank=True, verbose_name="Fabricante")
    modelo = models.CharField(max_length=120, blank=True, verbose_name="Modelo")
    numero_serie = models.CharField(max_length=120, blank=True, db_index=True, verbose_name="Número de Série")
    area = models.ForeignKey(
        PcpAreaProducao,
        on_delete=models.PROTECT,
        related_name="ativos",
        db_index=True,
        verbose_name="Área de Produção",
    )
    status = models.CharField(
        max_length=20,
        choices=StatusAtivo.choices,
        default=StatusAtivo.OPERANDO,
        db_index=True,
        verbose_name="Status",
    )
    criticidade = models.CharField(
        max_length=20,
        choices=CriticidadeAtivo.choices,
        default=CriticidadeAtivo.MEDIA,
        db_index=True,
        verbose_name="Criticidade",
    )

    class Meta:
        verbose_name = "Ativo PCP"
        verbose_name_plural = "Ativos PCP"
        db_table = "pcp_ativo"
        indexes = [
            models.Index(fields=["area", "ativo"], name="pcp_ativo_area_ativo_idx"),
            models.Index(fields=["status", "ativo"], name="pcp_ativo_status_idx"),
            models.Index(fields=["criticidade", "ativo"], name="pcp_ativo_criticidade_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nome}"


class PcpPlanoManutencao(SoftDeleteModel):
    ativo_pcp = models.ForeignKey(
        PcpAtivo,
        on_delete=models.PROTECT,
        related_name="planos_manutencao",
        db_index=True,
        verbose_name="Ativo",
    )
    tipo = models.CharField(
        max_length=20,
        choices=TipoManutencao.choices,
        default=TipoManutencao.PREVENTIVA,
        db_index=True,
        verbose_name="Tipo",
    )
    nome = models.CharField(max_length=150, db_index=True, verbose_name="Nome")
    descricao = models.TextField(blank=True, verbose_name="Descrição")
    intervalo_dias = models.PositiveIntegerField(null=True, blank=True, verbose_name="Intervalo em dias")
    data_inicio = models.DateField(db_index=True, verbose_name="Data de início")

    class Meta:
        verbose_name = "Plano de Manutenção"
        verbose_name_plural = "Planos de Manutenção"
        db_table = "pcp_plano_manutencao"
        constraints = [
            models.CheckConstraint(
                check=models.Q(ativo=False) | models.Q(intervalo_dias__gt=0),
                name="pcp_plano_ativo_exige_intervalo",
            ),
        ]
        indexes = [
            models.Index(fields=["ativo_pcp", "ativo"], name="pcp_plano_ativo_idx"),
            models.Index(fields=["tipo", "ativo"], name="pcp_plano_tipo_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ativo_pcp.codigo} - {self.nome}"


class PcpProgramacaoManutencao(SoftDeleteModel):
    plano = models.ForeignKey(
        PcpPlanoManutencao,
        on_delete=models.PROTECT,
        related_name="programacoes",
        db_index=True,
        verbose_name="Plano",
    )
    data_prevista = models.DateField(db_index=True, verbose_name="Data prevista")
    data_limite = models.DateField(null=True, blank=True, db_index=True, verbose_name="Data limite")
    status = models.CharField(
        max_length=20,
        choices=StatusManutencao.choices,
        default=StatusManutencao.PLANEJADA,
        db_index=True,
        verbose_name="Status",
    )
    origem = models.CharField(
        max_length=20,
        choices=OrigemApontamento.choices,
        default=OrigemApontamento.SISTEMA,
        db_index=True,
        verbose_name="Origem",
    )

    class Meta:
        verbose_name = "Programação de Manutenção"
        verbose_name_plural = "Programações de Manutenção"
        db_table = "pcp_programacao_manutencao"
        constraints = [
            models.UniqueConstraint(
                fields=["plano", "data_prevista"],
                condition=models.Q(ativo=True),
                name="pcp_programacao_plano_data_uniq",
            ),
            models.UniqueConstraint(
                fields=["plano"],
                condition=models.Q(
                    ativo=True,
                    status__in=[StatusManutencao.PLANEJADA, StatusManutencao.EM_EXECUCAO],
                ),
                name="pcp_programacao_pendente_plano_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(data_limite__isnull=True) | models.Q(data_limite__gte=models.F("data_prevista")),
                name="pcp_programacao_limite_gte_prevista",
            ),
        ]
        indexes = [
            models.Index(fields=["plano", "status"], name="pcp_prog_plano_status_idx"),
            models.Index(fields=["status", "data_prevista"], name="pcp_prog_status_data_idx"),
            models.Index(fields=["ativo", "data_prevista"], name="pcp_prog_ativo_flag_data_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.plano.ativo_pcp.codigo} - {self.data_prevista}"


class PcpExecucaoManutencao(SoftDeleteModel):
    protocolo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True, verbose_name="Protocolo")
    programacao = models.ForeignKey(
        PcpProgramacaoManutencao,
        on_delete=models.SET_NULL,
        related_name="execucoes",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Programação",
    )
    ativo_pcp = models.ForeignKey(
        PcpAtivo,
        on_delete=models.PROTECT,
        related_name="execucoes_manutencao",
        db_index=True,
        verbose_name="Ativo",
    )
    tipo = models.CharField(max_length=20, choices=TipoManutencao.choices, db_index=True, verbose_name="Tipo")
    data_inicio = models.DateTimeField(db_index=True, verbose_name="Data de início")
    data_fim = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Data de fim")
    observacao = models.TextField(blank=True, verbose_name="Observação")
    diagnostico = models.TextField(blank=True, verbose_name="Diagnóstico")
    servicos_executados = models.TextField(blank=True, verbose_name="Serviços executados")
    resultado = models.TextField(blank=True, verbose_name="Resultado")
    recomendacoes = models.TextField(blank=True, verbose_name="Recomendações")
    concluido_em = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Concluído em")
    concluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="execucoes_manutencao_concluidas_pcp",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Concluído por",
    )
    snapshot_ativo_codigo = models.CharField(max_length=50, blank=True, verbose_name="Código do ativo no fechamento")
    snapshot_ativo_nome = models.CharField(max_length=150, blank=True, verbose_name="Nome do ativo no fechamento")
    snapshot_ativo_numero_serie = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Número de série no fechamento",
    )
    snapshot_area_nome = models.CharField(max_length=120, blank=True, verbose_name="Área no fechamento")
    snapshot_plano_nome = models.CharField(max_length=150, blank=True, verbose_name="Plano no fechamento")
    snapshot_plano_tipo = models.CharField(max_length=20, blank=True, verbose_name="Tipo do plano no fechamento")
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="execucoes_manutencao_pcp",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Responsável",
    )

    class Meta:
        verbose_name = "Execução de Manutenção"
        verbose_name_plural = "Execuções de Manutenção"
        db_table = "pcp_execucao_manutencao"
        constraints = [
            models.UniqueConstraint(
                fields=["ativo_pcp"],
                condition=models.Q(ativo=True, data_fim__isnull=True),
                name="pcp_execucao_aberta_ativo_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(data_fim__isnull=True) | models.Q(data_fim__gt=models.F("data_inicio")),
                name="pcp_execucao_fim_gt_inicio",
            ),
        ]
        indexes = [
            models.Index(fields=["ativo_pcp", "data_inicio"], name="pcp_exec_ativo_inicio_idx"),
            models.Index(fields=["tipo", "data_inicio"], name="pcp_exec_tipo_inicio_idx"),
            models.Index(fields=["responsavel", "data_inicio"], name="pcp_exec_resp_inicio_idx"),
            models.Index(fields=["concluido_em", "ativo"], name="pcp_exec_concluido_idx"),
        ]
        permissions = [
            ("corrigir_execucao_concluida", "Pode corrigir execução de manutenção concluída"),
        ]

    def __str__(self) -> str:
        return f"{self.ativo_pcp.codigo} - {self.tipo} - {self.data_inicio:%Y-%m-%d}"


class PcpEvidenciaManutencao(SoftDeleteModel):
    execucao = models.ForeignKey(
        PcpExecucaoManutencao,
        on_delete=models.PROTECT,
        related_name="evidencias",
        db_index=True,
        verbose_name="Execução",
    )
    finalidade = models.CharField(
        max_length=30,
        choices=FinalidadeEvidencia.choices,
        db_index=True,
        verbose_name="Finalidade",
    )
    arquivo = models.FileField(
        upload_to=evidencia_manutencao_upload_to,
        storage=pcp_private_storage,
        max_length=500,
        verbose_name="Arquivo",
    )
    tipo = models.CharField(max_length=20, choices=TipoEvidencia.choices, db_index=True, verbose_name="Tipo")
    nome_original = models.CharField(max_length=255, verbose_name="Nome original")
    tipo_mime = models.CharField(max_length=100, verbose_name="Tipo MIME")
    tamanho_bytes = models.PositiveBigIntegerField(verbose_name="Tamanho em bytes")
    sha256 = models.CharField(max_length=64, db_index=True, verbose_name="SHA-256")
    descricao = models.CharField(max_length=255, blank=True, verbose_name="Descrição")
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="evidencias_manutencao_pcp",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Enviado por",
    )

    class Meta:
        verbose_name = "Evidência de Manutenção"
        verbose_name_plural = "Evidências de Manutenção"
        db_table = "pcp_evidencia_manutencao"
        indexes = [
            models.Index(fields=["execucao", "ativo"], name="pcp_evid_exec_ativo_idx"),
            models.Index(fields=["tipo", "ativo"], name="pcp_evid_tipo_ativo_idx"),
            models.Index(fields=["execucao", "finalidade", "ativo"], name="pcp_evid_exec_final_idx"),
        ]
        permissions = [
            ("desativar_evidencia_manutencao", "Pode desativar evidência de manutenção"),
        ]

    def __str__(self) -> str:
        return f"{self.execucao.protocolo} - {self.nome_original}"


class PcpEventoAuditoriaManutencao(models.Model):
    execucao = models.ForeignKey(
        PcpExecucaoManutencao,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
        db_index=True,
        verbose_name="Execução",
    )
    tipo_evento = models.CharField(
        max_length=40,
        choices=TipoEventoAuditoria.choices,
        db_index=True,
        verbose_name="Tipo de evento",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="eventos_auditoria_manutencao_pcp",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Usuário",
    )
    justificativa = models.TextField(blank=True, verbose_name="Justificativa")
    dados = models.JSONField(default=dict, blank=True, verbose_name="Dados do evento")
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Criado em")

    objects = ImmutableAuditManager()

    class Meta:
        verbose_name = "Evento de Auditoria de Manutenção"
        verbose_name_plural = "Eventos de Auditoria de Manutenção"
        db_table = "pcp_evento_auditoria_manutencao"
        indexes = [
            models.Index(fields=["execucao", "criado_em"], name="pcp_audit_exec_criado_idx"),
            models.Index(fields=["tipo_evento", "criado_em"], name="pcp_audit_tipo_criado_idx"),
        ]
        default_permissions = ("add", "view")

    def __str__(self) -> str:
        return f"{self.execucao.protocolo} - {self.tipo_evento}"

    def delete(self, using: str | None = None, keep_parents: bool = False) -> None:
        raise ValueError("Eventos de auditoria não podem ser excluídos.")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk and PcpEventoAuditoriaManutencao.objects.filter(pk=self.pk).exists():
            raise ValueError("Eventos de auditoria não podem ser alterados.")
        super().save(*args, **kwargs)


class PcpDowntime(SoftDeleteModel):
    ativo_pcp = models.ForeignKey(
        PcpAtivo,
        on_delete=models.PROTECT,
        related_name="downtimes",
        db_index=True,
        verbose_name="Ativo",
    )
    categoria = models.CharField(
        max_length=30,
        choices=CategoriaDowntime.choices,
        db_index=True,
        verbose_name="Categoria",
    )
    tipo = models.CharField(max_length=30, choices=TipoDowntime.choices, db_index=True, verbose_name="Tipo")
    inicio = models.DateTimeField(db_index=True, verbose_name="Início")
    fim = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Fim")
    duracao_minutos = models.PositiveIntegerField(null=True, blank=True, db_index=True, verbose_name="Duração em minutos")
    motivo = models.CharField(max_length=255, db_index=True, verbose_name="Motivo")
    observacao = models.TextField(blank=True, verbose_name="Observação")
    origem = models.CharField(
        max_length=20,
        choices=OrigemApontamento.choices,
        default=OrigemApontamento.MANUAL,
        db_index=True,
        verbose_name="Origem",
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="downtimes_pcp",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Responsável",
    )

    class Meta:
        verbose_name = "Downtime PCP"
        verbose_name_plural = "Downtimes PCP"
        db_table = "pcp_downtime"
        constraints = [
            models.UniqueConstraint(
                fields=["ativo_pcp"],
                condition=models.Q(ativo=True, fim__isnull=True),
                name="pcp_downtime_aberto_ativo_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(fim__isnull=True) | models.Q(fim__gt=models.F("inicio")),
                name="pcp_downtime_fim_gt_inicio",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(
                        categoria=CategoriaDowntime.TEMPO_PRODUCAO_PERDIDO,
                        tipo__in=(*TIPOS_DOWNTIME_TEMPO_PRODUCAO, *TIPOS_DOWNTIME_LEGADOS),
                    )
                    | models.Q(
                        categoria=CategoriaDowntime.TEMPO_OCIOSO,
                        tipo__in=TIPOS_DOWNTIME_TEMPO_OCIOSO,
                    )
                ),
                name="pcp_downtime_categoria_tipo_valido",
            ),
        ]
        indexes = [
            models.Index(fields=["ativo_pcp", "inicio"], name="pcp_down_ativo_inicio_idx"),
            models.Index(fields=["tipo", "inicio"], name="pcp_down_tipo_inicio_idx"),
            models.Index(fields=["categoria", "inicio"], name="pcp_down_categoria_inicio_idx"),
            models.Index(fields=["fim", "ativo"], name="pcp_down_fim_ativo_idx"),
            models.Index(fields=["origem", "inicio"], name="pcp_down_origem_inicio_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ativo_pcp.codigo} - {self.inicio:%Y-%m-%d %H:%M}"


class PcpParametroAlerta(SoftDeleteModel):
    ativo_pcp = models.ForeignKey(
        PcpAtivo,
        on_delete=models.PROTECT,
        related_name="parametros_alerta",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Ativo",
    )
    area = models.ForeignKey(
        PcpAreaProducao,
        on_delete=models.PROTECT,
        related_name="parametros_alerta",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Área",
    )
    dias_antecedencia = models.PositiveIntegerField(default=7, verbose_name="Dias de antecedência")
    emails_destino = models.TextField(verbose_name="E-mails de destino")
    alertar_preventiva = models.BooleanField(default=True, verbose_name="Alertar preventiva")
    alertar_downtime_aberto = models.BooleanField(default=True, verbose_name="Alertar downtime aberto")

    class Meta:
        verbose_name = "Parâmetro de Alerta PCP"
        verbose_name_plural = "Parâmetros de Alerta PCP"
        db_table = "pcp_parametro_alerta"
        constraints = [
            models.CheckConstraint(
                check=~models.Q(ativo_pcp__isnull=False, area__isnull=False),
                name="pcp_parametro_alerta_um_alvo",
            ),
        ]
        indexes = [
            models.Index(fields=["ativo_pcp", "ativo"], name="pcp_alerta_ativo_idx"),
            models.Index(fields=["area", "ativo"], name="pcp_alerta_area_idx"),
        ]

    def __str__(self) -> str:
        if self.ativo_pcp_id:
            alvo = self.ativo_pcp.codigo
        elif self.area_id:
            alvo = self.area.codigo
        else:
            alvo = "global"
        return f"Alerta PCP - {alvo}"


class PcpAlertaEnviado(SoftDeleteModel):
    tipo_alerta = models.CharField(max_length=30, choices=TipoAlerta.choices, db_index=True, verbose_name="Tipo")
    chave_idempotencia = models.CharField(max_length=120, unique=True, db_index=True, verbose_name="Chave de idempotência")
    parametro = models.ForeignKey(
        PcpParametroAlerta,
        on_delete=models.SET_NULL,
        related_name="alertas_enviados",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Parâmetro",
    )
    programacao = models.ForeignKey(
        PcpProgramacaoManutencao,
        on_delete=models.SET_NULL,
        related_name="alertas_enviados",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Programação",
    )
    programacao_alerta = models.ForeignKey(
        "PcpProgramacaoAlertaManutencao",
        on_delete=models.SET_NULL,
        related_name="envios",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Programação do alerta",
    )
    downtime = models.ForeignKey(
        PcpDowntime,
        on_delete=models.SET_NULL,
        related_name="alertas_enviados",
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Downtime",
    )
    data_referencia = models.DateField(db_index=True, verbose_name="Data de referência")
    destinatarios = models.TextField(verbose_name="Destinatários")
    assunto = models.CharField(max_length=180, verbose_name="Assunto")
    status = models.CharField(
        max_length=20,
        choices=StatusAlerta.choices,
        default=StatusAlerta.PENDENTE,
        db_index=True,
        verbose_name="Status",
    )
    tentativas = models.PositiveIntegerField(default=0, verbose_name="Tentativas")
    ultimo_erro = models.TextField(blank=True, verbose_name="Último erro")
    enviado_em = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Enviado em")

    class Meta:
        verbose_name = "Alerta Enviado PCP"
        verbose_name_plural = "Alertas Enviados PCP"
        db_table = "pcp_alerta_enviado"
        indexes = [
            models.Index(fields=["tipo_alerta", "data_referencia"], name="pcp_alerta_env_tipo_data_idx"),
            models.Index(fields=["status", "ativo"], name="pcp_alerta_env_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.tipo_alerta} - {self.data_referencia}"


class PcpProgramacaoAlertaManutencao(SoftDeleteModel):
    programacao = models.ForeignKey(
        PcpProgramacaoManutencao,
        on_delete=models.PROTECT,
        related_name="programacoes_alerta",
        db_index=True,
        verbose_name="Programação de manutenção",
    )
    dias_antecedencia = models.PositiveSmallIntegerField(db_index=True, verbose_name="Dias de antecedência")
    data_disparo = models.DateField(db_index=True, verbose_name="Data programada para disparo")
    destinatarios = models.TextField(verbose_name="Destinatários")
    status = models.CharField(
        max_length=20,
        choices=StatusAlerta.choices,
        default=StatusAlerta.PENDENTE,
        db_index=True,
        verbose_name="Status",
    )
    tentativas = models.PositiveIntegerField(default=0, verbose_name="Tentativas")
    ultimo_erro = models.TextField(blank=True, verbose_name="Último erro")
    enviado_em = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Enviado em")

    class Meta:
        verbose_name = "Programação de Alerta de Manutenção"
        verbose_name_plural = "Programações de Alertas de Manutenção"
        db_table = "pcp_programacao_alerta_manutencao"
        constraints = [
            models.UniqueConstraint(
                fields=["programacao", "dias_antecedencia", "destinatarios"],
                condition=models.Q(ativo=True),
                name="pcp_prog_alerta_marco_dest_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(dias_antecedencia__in=MARCOS_ALERTA_PREVENTIVA),
                name="pcp_prog_alerta_marco_valido",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "data_disparo"], name="pcp_prgalrt_status_data_idx"),
            models.Index(fields=["programacao", "ativo"], name="pcp_prog_alerta_prog_ativo_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.programacao} - {self.dias_antecedencia} dias"
