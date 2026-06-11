from __future__ import annotations

from django.db import migrations, models
from django.db.models import Min


def preencher_data_inicio(apps: object, schema_editor: object) -> None:
    plano_model = apps.get_model("pcp", "PcpPlanoManutencao")
    alias = schema_editor.connection.alias
    planos = plano_model.objects.using(alias).annotate(
        primeira_programacao=Min("programacoes__data_prevista")
    )

    for plano in planos.iterator(chunk_size=500):
        data_inicio = plano.primeira_programacao or plano.created_at.date()
        plano_model.objects.using(alias).filter(pk=plano.pk).update(data_inicio=data_inicio)


class Migration(migrations.Migration):
    dependencies = [
        ("pcp", "0009_alter_movimentacaoestoquepcp_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pcpplanomanutencao",
            name="data_inicio",
            field=models.DateField(blank=True, null=True, verbose_name="Data de início"),
        ),
        migrations.RunPython(preencher_data_inicio, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pcpplanomanutencao",
            name="data_inicio",
            field=models.DateField(db_index=True, verbose_name="Data de início"),
        ),
    ]
