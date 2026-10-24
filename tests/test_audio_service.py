from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from backend.core.config import settings
from backend.services.audio_service import store_original_audio


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.anyio
async def test_store_original_audio_hashes_and_uses_internal_name(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    upload = make_upload("muestra original.wav", b"audio-data", "audio/wav")

    stored = await store_original_audio(upload)

    assert stored.original_name == "muestra original.wav"
    assert stored.extension == "wav"
    assert stored.sha256 == "9987d4dfea80e5280a1a5e03a72cb35cff47c255c9bcc1fc3bf65373d92660e6"
    assert stored.path.name != stored.original_name
    assert stored.path.read_bytes() == b"audio-data"


@pytest.mark.anyio
async def test_store_original_audio_rejects_unknown_extension(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    upload = make_upload("muestra.exe", b"not-audio", "application/octet-stream")

    with pytest.raises(ValueError, match="Formato"):
        await store_original_audio(upload)


@pytest.mark.anyio
async def test_store_original_audio_enforces_size_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(settings, "max_audio_size_mb", 0)
    upload = make_upload("muestra.wav", b"audio-data", "audio/wav")

    with pytest.raises(ValueError, match="tamaño máximo"):
        await store_original_audio(upload)

    assert list(tmp_path.rglob("*.wav")) == []
