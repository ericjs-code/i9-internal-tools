from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pcp.models import PcpPlanoManutencao, StatusManutencao


class PcpPlanoManutencaoPDFService:
    @classmethod
    def gerar_response(cls, *, plano: PcpPlanoManutencao, emissor: Any) -> HttpResponse:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.4 * cm,
            leftMargin=1.4 * cm,
            topMargin=1.2 * cm,
            bottomMargin=1.2 * cm,
            title="Plano de Manutenção",
        )

        styles = cls._styles()
        elementos: list[Any] = []
        elementos.extend(cls._cabecalho(plano=plano, styles=styles))
        elementos.append(Spacer(1, 0.3 * cm))
        elementos.append(cls._tabela_identificacao(plano=plano, emissor=emissor, styles=styles))
        elementos.append(Spacer(1, 0.35 * cm))
        elementos.append(Paragraph("Itens de manutenção", styles["section_title"]))
        elementos.append(cls._itens_manutencao(plano=plano, styles=styles))
        elementos.append(Spacer(1, 0.8 * cm))
        elementos.append(cls._assinaturas(styles=styles))

        doc.build(elementos, onFirstPage=cls._rodape, onLaterPages=cls._rodape)

        filename = f"plano_manutencao_{cls._slug(plano.ativo_pcp.codigo)}_{plano.pk}.pdf"
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    @classmethod
    def _cabecalho(cls, *, plano: PcpPlanoManutencao, styles: dict[str, ParagraphStyle]) -> list[Any]:
        logo = cls._logo()
        titulo = Paragraph("Plano de Manutenção", styles["title"])
        subtitulo = Paragraph(
            cls._safe(f"{plano.ativo_pcp.codigo} - {plano.ativo_pcp.nome}"),
            styles["subtitle"],
        )
        texto = [titulo, Spacer(1, 0.1 * cm), subtitulo]
        if logo:
            tabela = Table([[logo, texto]], colWidths=[3.1 * cm, 13.1 * cm])
        else:
            tabela = Table([[Paragraph("I9", styles["logo_fallback"]), texto]], colWidths=[3.1 * cm, 13.1 * cm])
        tabela.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#D9E2EC")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return [tabela]

    @classmethod
    def _tabela_identificacao(
        cls,
        *,
        plano: PcpPlanoManutencao,
        emissor: Any,
        styles: dict[str, ParagraphStyle],
    ) -> Table:
        ativo = plano.ativo_pcp
        linhas = [
            ("Código do ativo", ativo.codigo, "Nome do ativo", ativo.nome),
            ("Status do ativo", ativo.get_status_display(), "Criticidade", ativo.get_criticidade_display()),
            ("Fabricante", ativo.fabricante or "-", "Modelo", ativo.modelo or "-"),
            ("Número de série", ativo.numero_serie or "-", "Tipo do plano", plano.get_tipo_display()),
            ("Data de início", cls._data(plano.data_inicio), "Recorrência", cls._recorrencia(plano)),
            ("Próxima manutenção", cls._proxima_manutencao(plano), "Plano", plano.nome),
            ("Emitido em", cls._data_hora(timezone.now()), "Emitido por", cls._nome_usuario(emissor)),
            ("Descrição do ativo", ativo.descricao or "-", "Descrição do plano", plano.descricao or "-"),
        ]
        dados = []
        for label_a, valor_a, label_b, valor_b in linhas:
            dados.append(
                [
                    Paragraph(cls._safe(label_a), styles["label"]),
                    Paragraph(cls._safe(valor_a), styles["value"]),
                    Paragraph(cls._safe(label_b), styles["label"]),
                    Paragraph(cls._safe(valor_b), styles["value"]),
                ]
            )
        tabela = Table(dados, colWidths=[3.0 * cm, 5.1 * cm, 3.0 * cm, 5.1 * cm], repeatRows=0)
        tabela.setStyle(cls._table_style())
        return tabela

    @classmethod
    def _itens_manutencao(cls, *, plano: PcpPlanoManutencao, styles: dict[str, ParagraphStyle]) -> Table:
        itens_planejados = list(plano.itens_planejados.all())
        if not itens_planejados:
            rows = [[Paragraph("Nenhum item de manutenção associado ao plano.", styles["muted"])]]
            tabela = Table(rows, colWidths=[16.2 * cm])
            tabela.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            return tabela

        rows = [
            [
                Paragraph("[ ]", styles["checkbox"]),
                Paragraph(cls._safe(item.item_manutencao.descricao), styles["value"]),
            ]
            for item in itens_planejados
        ]
        tabela = Table(rows, colWidths=[1.0 * cm, 15.2 * cm], repeatRows=0)
        tabela.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E6EEF5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return tabela

    @classmethod
    def _assinaturas(cls, *, styles: dict[str, ParagraphStyle]) -> Table:
        linha = "_" * 36
        dados = [
            [
                Paragraph(linha, styles["signature_line"]),
                Paragraph(linha, styles["signature_line"]),
            ],
            [
                Paragraph("Assinatura I9", styles["signature_label"]),
                Paragraph("Assinatura Prestador de Serviço", styles["signature_label"]),
            ],
        ]
        tabela = Table(dados, colWidths=[8.1 * cm, 8.1 * cm])
        tabela.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return tabela

    @staticmethod
    def _rodape(canvas: Any, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(A4[0] - 1.4 * cm, 0.7 * cm, f"Página {doc.page}")
        canvas.restoreState()

    @classmethod
    def _logo(cls) -> Image | None:
        for relative_path in (
            Path("static") / "img" / "logo_card_i9tmg.png",
            Path("static") / "img" / "logo.jpg",
        ):
            path = settings.BASE_DIR / relative_path
            if path.exists():
                try:
                    logo = Image(str(path))
                    ratio = logo.imageWidth / logo.imageHeight
                    logo.drawHeight = 1.45 * cm
                    logo.drawWidth = logo.drawHeight * ratio
                    return logo
                except Exception:
                    return None
        return None

    @staticmethod
    def _table_style() -> TableStyle:
        return TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9E2EC")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E6EEF5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F8FAFC")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )

    @staticmethod
    def _styles() -> dict[str, ParagraphStyle]:
        sample = getSampleStyleSheet()
        normal = sample["Normal"]
        return {
            "title": ParagraphStyle(
                "PcpPdfTitle",
                parent=normal,
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=19,
                alignment=TA_LEFT,
                textColor=colors.HexColor("#0F3760"),
            ),
            "subtitle": ParagraphStyle(
                "PcpPdfSubtitle",
                parent=normal,
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#475569"),
            ),
            "section_title": ParagraphStyle(
                "PcpPdfSectionTitle",
                parent=normal,
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=colors.HexColor("#0F3760"),
                spaceAfter=6,
            ),
            "label": ParagraphStyle(
                "PcpPdfLabel",
                parent=normal,
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#334155"),
            ),
            "value": ParagraphStyle("PcpPdfValue", parent=normal, fontSize=8, leading=10.5),
            "muted": ParagraphStyle(
                "PcpPdfMuted",
                parent=normal,
                fontSize=8,
                leading=10.5,
                textColor=colors.HexColor("#64748B"),
            ),
            "checkbox": ParagraphStyle(
                "PcpPdfCheckbox",
                parent=normal,
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=11,
                alignment=TA_CENTER,
            ),
            "logo_fallback": ParagraphStyle(
                "PcpPdfLogoFallback",
                parent=normal,
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=26,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#0F3760"),
            ),
            "signature_line": ParagraphStyle(
                "PcpPdfSignatureLine",
                parent=normal,
                fontSize=8,
                leading=10,
                alignment=TA_CENTER,
            ),
            "signature_label": ParagraphStyle(
                "PcpPdfSignatureLabel",
                parent=normal,
                fontSize=8,
                leading=10,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#334155"),
            ),
        }

    @staticmethod
    def _safe(valor: Any) -> str:
        return escape(str(valor or "-")).replace("\n", "<br/>")

    @staticmethod
    def _data(valor: Any) -> str:
        if not valor:
            return "-"
        return valor.strftime("%d/%m/%Y")

    @staticmethod
    def _data_hora(valor: Any) -> str:
        if not valor:
            return "-"
        return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _recorrencia(plano: PcpPlanoManutencao) -> str:
        if not plano.intervalo_dias:
            return "-"
        return f"A cada {plano.intervalo_dias} dias"

    @staticmethod
    def _proxima_manutencao(plano: PcpPlanoManutencao) -> str:
        programacoes = [
            programacao
            for programacao in plano.programacoes.all()
            if programacao.status == StatusManutencao.PLANEJADA
        ]
        if not programacoes:
            return "Sem programação ativa"
        programacao = sorted(programacoes, key=lambda item: (item.data_prevista, item.id))[0]
        return programacao.data_prevista.strftime("%d/%m/%Y")

    @staticmethod
    def _nome_usuario(user: Any) -> str:
        if not user:
            return "-"
        nome = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return nome or getattr(user, "username", "-")

    @staticmethod
    def _slug(valor: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", valor.strip().lower())
        return slug.strip("_") or "plano"
