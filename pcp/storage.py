from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PcpPrivateStorage(FileSystemStorage):
    def __init__(self) -> None:
        super().__init__(location=settings.PCP_PRIVATE_MEDIA_ROOT, base_url=None)
