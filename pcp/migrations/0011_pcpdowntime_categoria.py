from __future__ import annotations

from django.db import migrations, models


TEMPO_PRODUCAO_PERDIDO = "tempo_producao_perdido"
TEMPO_OCIOSO = "tempo_ocioso"
TIPOS_TEMPO_PRODUCAO = (
    "falta_mao_obra",
    "maquinario_estragou",
    "falta_material",
    "manutencao",
    "nao_planejado",
    "planejado",
    "setup",
    "qualidade",
)
TIPOS_TEMPO_OCIOSO = ("falta_desenho",)


def preencher_categoria_downtime(apps: object, schema_editor: object) -> None:
    downtime_model = apps.get_model("pcp", "PcpDowntime")
    alias = schema_editor.connection.alias
    downtime_model._base_manager.using(alias).filter(categoria__isnull=True).update(
        categoria=TEMPO_PRODUCAO_PERDIDO
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pcp", "0010_pcpplanomanutencao_data_inicio"),
    ]

    operations = [
        migrations.AddField(
            model_name="pcpdowntime",
            name="categoria",
            field=models.CharField(
                blank=True,
                choices=[
                    (TEMPO_PRODUCAO_PERDIDO, "Tempo de Produção (Perdido)"),
                    (TEMPO_OCIOSO, "Tempo Ocioso"),
                ],
                max_length=30,
                null=True,
                verbose_name="Categoria",
            ),
        ),
        migrations.RunPython(preencher_categoria_downtime, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pcpdowntime",
            name="categoria",
            field=models.CharField(
                choices=[
                    (TEMPO_PRODUCAO_PERDIDO, "Tempo de Produção (Perdido)"),
                    (TEMPO_OCIOSO, "Tempo Ocioso"),
                ],
                db_index=True,
                max_length=30,
                verbose_name="Categoria",
            ),
        ),
        migrations.AlterField(
            model_name="pcpdowntime",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("falta_mao_obra", "Falta de mão de obra"),
                    ("maquinario_estragou", "Maquinário estragou"),
                    ("falta_material", "Falta de material"),
                    ("manutencao", "Manutenção"),
                    ("falta_desenho", "Falta de desenho"),
                ],
                db_index=True,
                max_length=30,
                verbose_name="Tipo",
            ),
        ),
        migrations.AddIndex(
            model_name="pcpdowntime",
            index=models.Index(fields=["categoria", "inicio"], name="pcp_down_categoria_inicio_idx"),
        ),
        migrations.AddConstraint(
            model_name="pcpdowntime",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(categoria=TEMPO_PRODUCAO_PERDIDO, tipo__in=TIPOS_TEMPO_PRODUCAO)
                    | models.Q(categoria=TEMPO_OCIOSO, tipo__in=TIPOS_TEMPO_OCIOSO)
                ),
                name="pcp_downtime_categoria_tipo_valido",
            ),
        ),
    ]
