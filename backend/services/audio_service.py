from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.core.config import settings

ALLOWED_AUDIO_MIME_TYPES = {
    ".mp3": {"audio/mpeg", "audio/mp3", "application/octet-stream"},
    ".ogg": {"audio/ogg", "application/ogg", "application/octet-stream"},
    ".mp4": {"audio/mp4", "video/mp4", "application/octet-stream"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "application/octet-stream"},
}


@dataclass(frozen=True)
class StoredAudio:
    path: Path
    original_name: str
    extension: str
    sha256: str
    size_bytes: int


def _storage_directory(category: str) -> Path:
    if category not in {"referencias", "consultas"}:
        raise ValueError("Categoría de almacenamiento no permitida")
    directory = Path(settings.storage_root) / category / "originales"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validated_extension(filename: str | None, content_type: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_AUDIO_MIME_TYPES:
        raise ValueError("Formato de audio no permitido")
    if content_type and content_type.lower() not in ALLOWED_AUDIO_MIME_TYPES[extension]:
        raise ValueError("El tipo MIME no coincide con la extensión")
    return extension


async def store_original_audio(
    upload: UploadFile,
    category: str = "referencias",
) -> StoredAudio:
    extension = _validated_extension(upload.filename, upload.content_type)
    destination = _storage_directory(category) / f"{uuid4().hex}{extension}"
    digest = sha256()
    total_size = 0
    max_size = settings.max_audio_size_mb * 1024 * 1024

    try:
        with destination.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > max_size:
                    raise ValueError("El archivo supera el tamaño máximo permitido")
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredAudio(
        path=destination,
        original_name=upload.filename or "audio",
        extension=extension.removeprefix("."),
        sha256=digest.hexdigest(),
        size_bytes=total_size,
    )


async def copy_analysis_original(
    source_path: str, original_name: str, original_format: str, expected_hash: str,
) -> StoredAudio:
    """Copy a stored query, checking the copied bytes against its recorded hash."""
    if len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
        raise ValueError("Hash de audio original inválido")
    project_root = Path(__file__).resolve().parents[2]
    storage_root = Path(settings.storage_root).resolve()
    if not storage_root.is_relative_to(project_root / "storage"):
        raise ValueError("Almacenamiento fuera del directorio autorizado")
    query_root = (storage_root / "consultas" / "originales").resolve()
    reference_root = (storage_root / "referencias" / "originales").resolve()
    processed_root = (storage_root / "referencias" / "procesados").resolve()
    if any(not directory.is_relative_to(storage_root) for directory in (query_root, reference_root, processed_root)):
        raise ValueError("Almacenamiento fuera del directorio autorizado")
    source = Path(source_path).resolve()
    if not source.is_relative_to(query_root) or not source.is_file():
        raise ValueError("El audio original no está disponible")
    extension = _validated_extension(original_name, None).removeprefix(".")
    if extension != original_format or source.suffix.lower() != f".{extension}":
        raise ValueError("El formato del audio original no coincide")
    with source.open("rb") as stream:
        stored = await store_original_audio(
            UploadFile(file=stream, filename=original_name), category="referencias",
        )
    if not stored.size_bytes or not compare_digest(stored.sha256, expected_hash):
        stored.path.unlink(missing_ok=True)
        raise ValueError("No se pudo verificar la integridad del audio original")
    return stored
