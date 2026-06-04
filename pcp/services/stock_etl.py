from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction

from core.services.protheus_etl import ProtheusBaseETL
from pcp.models import MovimentacaoEstoquePCP, OrigemMovimentacao, TipoMovimentacao


logger = logging.getLogger(__name__)


class PCPEstoqueETLService(ProtheusBaseETL):
    ARQUIVOS_ALVO = ["sd10101.sdb", "sd20101.sdb", "sd30101.sdb"]
    BATCH_SIZE = 2000

    @classmethod
    def transformar_e_salvar(cls, dados_brutos: dict[str, pd.DataFrame]) -> bool:
        dataframes = [
            dataframe
            for dataframe in (
                cls._transformar_sd1(dados_brutos.get("sd1")),
                cls._transformar_sd2(dados_brutos.get("sd2")),
                cls._transformar_sd3(dados_brutos.get("sd3")),
            )
            if dataframe is not None and not dataframe.empty
        ]
        if not dataframes:
            logger.warning("[%s] Nenhuma movimentação válida foi processada.", cls.__name__)
            return False

        colunas_chave = [
            "filial",
            "produto_codigo",
            "data_movimentacao",
            "tipo_movimentacao",
            "origem_movimentacao",
            "documento",
            "cf_operacao",
        ]
        dataframe_final = pd.concat(dataframes, ignore_index=True)
        dataframe_final["quantidade"] = pd.to_numeric(dataframe_final["quantidade"], errors="coerce").fillna(0).abs()
        dataframe_final = dataframe_final.groupby(colunas_chave, as_index=False, dropna=False)["quantidade"].sum()
        cls._realizar_upsert_lote(dataframe_final)
        return True

    @classmethod
    def _transformar_sd1(cls, dataframe: pd.DataFrame | None) -> pd.DataFrame | None:
        colunas = ["D1_FILIAL", "D1_COD", "D1_DTDIGIT", "D1_QUANT", "D1_DOC"]
        if not cls._possui_colunas(dataframe=dataframe, colunas=colunas, origem="SD1"):
            return None
        resultado = dataframe[colunas].copy()
        return cls._normalizar_dataframe(
            dataframe=resultado,
            filial="D1_FILIAL",
            produto="D1_COD",
            data="D1_DTDIGIT",
            quantidade="D1_QUANT",
            documento="D1_DOC",
            tipo=TipoMovimentacao.ENTRADA,
            origem=OrigemMovimentacao.NF_ENTRADA,
        )

    @classmethod
    def _transformar_sd2(cls, dataframe: pd.DataFrame | None) -> pd.DataFrame | None:
        colunas = ["D2_FILIAL", "D2_COD", "D2_EMISSAO", "D2_QUANT", "D2_DOC"]
        if not cls._possui_colunas(dataframe=dataframe, colunas=colunas, origem="SD2"):
            return None
        resultado = dataframe[colunas].copy()
        return cls._normalizar_dataframe(
            dataframe=resultado,
            filial="D2_FILIAL",
            produto="D2_COD",
            data="D2_EMISSAO",
            quantidade="D2_QUANT",
            documento="D2_DOC",
            tipo=TipoMovimentacao.SAIDA,
            origem=OrigemMovimentacao.NF_SAIDA,
        )

    @classmethod
    def _transformar_sd3(cls, dataframe: pd.DataFrame | None) -> pd.DataFrame | None:
        colunas = ["D3_FILIAL", "D3_COD", "D3_EMISSAO", "D3_QUANT", "D3_DOC", "D3_TM", "D3_CF"]
        if not cls._possui_colunas(dataframe=dataframe, colunas=colunas, origem="SD3"):
            return None

        resultado = dataframe[colunas].copy()
        resultado["D3_TM"] = resultado["D3_TM"].astype(str).str.strip().str.upper()
        resultado = resultado[resultado["D3_TM"].isin(["RE", "DE"])]
        resultado = cls._normalizar_dataframe(
            dataframe=resultado,
            filial="D3_FILIAL",
            produto="D3_COD",
            data="D3_EMISSAO",
            quantidade="D3_QUANT",
            documento="D3_DOC",
            tipo=TipoMovimentacao.ENTRADA,
            origem=OrigemMovimentacao.MOV_INTERNA,
            cf_operacao="D3_CF",
        )
        resultado["tipo_movimentacao"] = resultado["D3_TM"].map(
            {"RE": TipoMovimentacao.SAIDA, "DE": TipoMovimentacao.ENTRADA}
        )
        return resultado.drop(columns=["D3_TM"])

    @staticmethod
    def _normalizar_dataframe(
        *,
        dataframe: pd.DataFrame,
        filial: str,
        produto: str,
        data: str,
        quantidade: str,
        documento: str,
        tipo: str,
        origem: str,
        cf_operacao: str | None = None,
    ) -> pd.DataFrame:
        dataframe["filial"] = dataframe[filial].astype(str).str.strip()
        dataframe["produto_codigo"] = dataframe[produto].astype(str).str.strip()
        dataframe["data_movimentacao"] = pd.to_datetime(dataframe[data], format="%Y%m%d", errors="coerce").dt.date
        dataframe["quantidade"] = pd.to_numeric(dataframe[quantidade], errors="coerce")
        dataframe["documento"] = dataframe[documento].astype(str).str.strip().replace("nan", "")
        dataframe["tipo_movimentacao"] = tipo
        dataframe["origem_movimentacao"] = origem
        dataframe["cf_operacao"] = (
            dataframe[cf_operacao].astype(str).str.strip().replace("nan", "") if cf_operacao else ""
        )
        return dataframe.dropna(subset=["data_movimentacao", "quantidade"]).loc[
            lambda item: (item["filial"] != "") & (item["produto_codigo"] != "")
        ]

    @staticmethod
    def _possui_colunas(*, dataframe: pd.DataFrame | None, colunas: list[str], origem: str) -> bool:
        if dataframe is None:
            logger.warning("Arquivo %s não foi disponibilizado para o ETL do PCP.", origem)
            return False
        faltantes = set(colunas) - set(dataframe.columns)
        if faltantes:
            logger.warning("Arquivo %s sem colunas obrigatórias: %s", origem, sorted(faltantes))
            return False
        return True

    @classmethod
    def _realizar_upsert_lote(cls, dataframe: pd.DataFrame) -> None:
        registros = [
            MovimentacaoEstoquePCP(
                filial=str(registro["filial"]),
                produto_codigo=str(registro["produto_codigo"]),
                data_movimentacao=registro["data_movimentacao"],
                tipo_movimentacao=str(registro["tipo_movimentacao"]),
                origem_movimentacao=str(registro["origem_movimentacao"]),
                quantidade=cls._decimal_seguro(registro["quantidade"]),
                documento=str(registro["documento"]),
                cf_operacao=str(registro["cf_operacao"]),
            )
            for registro in dataframe.to_dict("records")
        ]
        with transaction.atomic():
            MovimentacaoEstoquePCP.objects.bulk_create(
                registros,
                batch_size=cls.BATCH_SIZE,
                update_conflicts=True,
                unique_fields=[
                    "filial",
                    "produto_codigo",
                    "data_movimentacao",
                    "tipo_movimentacao",
                    "origem_movimentacao",
                    "documento",
                    "cf_operacao",
                ],
                update_fields=["quantidade", "ativo", "updated_at"],
            )

    @staticmethod
    def _decimal_seguro(valor: object) -> Decimal:
        try:
            return Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")
