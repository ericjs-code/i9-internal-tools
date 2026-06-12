from __future__ import annotations

from django.db import migrations, models


SOLUCAO_DOCUMENTACAO = "solucao_documentacao"


def preencher_finalidade_evidencia(apps: object, schema_editor: object) -> None:
    evidencia_model = apps.get_model("pcp", "PcpEvidenciaManutencao")
    alias = schema_editor.connection.alias
    evidencia_model._base_manager.using(alias).filter(finalidade__isnull=True).update(
        finalidade=SOLUCAO_DOCUMENTACAO
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pcp", "0011_pcpdowntime_categoria"),
    ]

    operations = [
        migrations.AddField(
            model_name="pcpevidenciamanutencao",
            name="finalidade",
            field=models.CharField(
                blank=True,
                choices=[
                    ("problema", "Evidência do problema"),
                    (SOLUCAO_DOCUMENTACAO, "Evidência da solução / documentação"),
                ],
                max_length=30,
                null=True,
                verbose_name="Finalidade",
            ),
        ),
        migrations.RunPython(preencher_finalidade_evidencia, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pcpevidenciamanutencao",
            name="finalidade",
            field=models.CharField(
                choices=[
                    ("problema", "Evidência do problema"),
                    (SOLUCAO_DOCUMENTACAO, "Evidência da solução / documentação"),
                ],
                db_index=True,
                max_length=30,
                verbose_name="Finalidade",
            ),
        ),
        migrations.AddIndex(
            model_name="pcpevidenciamanutencao",
            index=models.Index(
                fields=["execucao", "finalidade", "ativo"],
                name="pcp_evid_exec_final_idx",
            ),
        ),
    ]
