from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from pcp.models import (
    FinalidadeEvidencia,
    PcpEvidenciaManutencao,
    PcpExecucaoManutencao,
    TipoEventoAuditoria,
    TipoEvidencia,
)
from pcp.services.audit import AuditoriaManutencaoService
from pcp.services.exceptions import PcpConflictError, PcpValidationError


class EvidenciaManutencaoService:
    EXTENSOES_PERMITIDAS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
    MIMES_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}

    @staticmethod
    def adicionar(
        *,
        execucao: PcpExecucaoManutencao,
        arquivo: UploadedFile,
        usuario: AbstractBaseUser | None,
        descricao: str = "",
        finalidade: str = FinalidadeEvidencia.SOLUCAO_DOCUMENTACAO,
    ) -> PcpEvidenciaManutencao:
        evidencias = EvidenciaManutencaoService.adicionar_multiplas(
            execucao=execucao,
            arquivos=((arquivo, descricao, finalidade),),
            usuario=usuario,
        )
        return evidencias[0]

    @staticmethod
    def adicionar_multiplas(
        *,
        execucao: PcpExecucaoManutencao,
        arquivos: Sequence[tuple[UploadedFile, str, str]],
        usuario: AbstractBaseUser | None,
    ) -> list[PcpEvidenciaManutencao]:
        if not arquivos:
            raise PcpValidationError("Informe ao menos uma evidência.")

        finalidades_validas = {valor for valor, _ in FinalidadeEvidencia.choices}
        arquivos_validados: list[tuple[UploadedFile, str, str, dict[str, str]]] = []
        for arquivo, descricao, finalidade in arquivos:
            if finalidade not in finalidades_validas:
                raise PcpValidationError("Finalidade da evidência inválida.")
            dados = EvidenciaManutencaoService._validar_e_ler(arquivo=arquivo)
            arquivos_validados.append((arquivo, descricao, finalidade, dados))

        evidencias_criadas: list[PcpEvidenciaManutencao] = []
        try:
            with transaction.atomic():
                execucao = PcpExecucaoManutencao.objects.select_for_update().get(pk=execucao.pk)
                quantidade = PcpEvidenciaManutencao.objects.filter(execucao=execucao).count()
                if quantidade + len(arquivos_validados) > settings.PCP_MAX_EVIDENCE_FILES:
                    raise PcpConflictError("Limite de evidências por manutenção atingido.")

                for arquivo, descricao, finalidade, dados in arquivos_validados:
                    evidencia = PcpEvidenciaManutencao.objects.create(
                        execucao=execucao,
                        finalidade=finalidade,
                        arquivo=arquivo,
                        tipo=dados["tipo"],
                        nome_original=Path(arquivo.name).name[:255],
                        tipo_mime=dados["tipo_mime"],
                        tamanho_bytes=arquivo.size,
                        sha256=dados["sha256"],
                        descricao=descricao.strip(),
                        enviado_por=usuario,
                    )
                    evidencias_criadas.append(evidencia)
                    AuditoriaManutencaoService.registrar(
                        execucao=execucao,
                        tipo_evento=TipoEventoAuditoria.EVIDENCIA_ADICIONADA,
                        usuario=usuario,
                        dados={
                            "evidencia_id": evidencia.pk,
                            "finalidade": evidencia.finalidade,
                            "nome_original": evidencia.nome_original,
                            "sha256": evidencia.sha256,
                        },
                    )
        except Exception:
            for evidencia in evidencias_criadas:
                evidencia.arquivo.storage.delete(evidencia.arquivo.name)
            raise

        return evidencias_criadas

    @staticmethod
    def desativar(
        *,
        evidencia: PcpEvidenciaManutencao,
        usuario: AbstractBaseUser | None,
        justificativa: str,
    ) -> PcpEvidenciaManutencao:
        if not justificativa.strip():
            raise PcpValidationError("Justificativa obrigatória para desativar a evidência.")

        with transaction.atomic():
            evidencia = PcpEvidenciaManutencao.objects.select_for_update().select_related("execucao").get(
                pk=evidencia.pk
            )
            evidencia.ativo = False
            evidencia.save(update_fields=["ativo", "updated_at"])
            AuditoriaManutencaoService.registrar(
                execucao=evidencia.execucao,
                tipo_evento=TipoEventoAuditoria.EVIDENCIA_DESATIVADA,
                usuario=usuario,
                justificativa=justificativa,
                dados={"evidencia_id": evidencia.pk, "nome_original": evidencia.nome_original},
            )
            return evidencia

    @staticmethod
    def _validar_e_ler(*, arquivo: UploadedFile) -> dict[str, str]:
        extensao = Path(arquivo.name).suffix.lower()
        tipo_mime = (getattr(arquivo, "content_type", "") or "").lower()
        if extensao not in EvidenciaManutencaoService.EXTENSOES_PERMITIDAS:
            raise PcpValidationError("Formato de evidência não permitido.")
        if tipo_mime not in EvidenciaManutencaoService.MIMES_PERMITIDOS:
            raise PcpValidationError("Tipo MIME da evidência não permitido.")
        if arquivo.size <= 0 or arquivo.size > settings.PCP_MAX_EVIDENCE_SIZE:
            raise PcpValidationError("Tamanho da evidência fora do limite permitido.")

        conteudo = arquivo.read()
        arquivo.seek(0)
        if extensao == ".pdf":
            if tipo_mime != "application/pdf" or not conteudo.startswith(b"%PDF-"):
                raise PcpValidationError("Arquivo PDF inválido.")
            tipo = TipoEvidencia.PDF
        else:
            if not tipo_mime.startswith("image/"):
                raise PcpValidationError("Arquivo de imagem inválido.")
            try:
                with Image.open(BytesIO(conteudo)) as imagem:
                    imagem.verify()
                    formato = (imagem.format or "").lower()
            except (UnidentifiedImageError, OSError) as exc:
                raise PcpValidationError("Arquivo de imagem inválido.") from exc
            extensoes_por_formato = {
                "jpeg": {".jpg", ".jpeg"},
                "png": {".png"},
                "webp": {".webp"},
            }
            mimes_por_formato = {
                "jpeg": "image/jpeg",
                "png": "image/png",
                "webp": "image/webp",
            }
            if extensao not in extensoes_por_formato.get(formato, set()) or tipo_mime != mimes_por_formato.get(formato):
                raise PcpValidationError("Extensão, MIME e conteúdo da imagem não correspondem.")
            tipo = TipoEvidencia.IMAGEM

        return {"tipo": tipo, "tipo_mime": tipo_mime, "sha256": sha256(conteudo).hexdigest()}
