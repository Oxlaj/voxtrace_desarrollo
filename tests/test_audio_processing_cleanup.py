import subprocess

import pytest

from backend.core.config import settings
from backend.services import audio_processing_service
from backend.services.audio_processing_service import AudioProcessingError, process_audio_copy


def test_processed_file_is_removed_when_ffmpeg_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    source = tmp_path / "original.wav"
    source.write_bytes(b"original")
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(command, 0, '{"streams":[{"codec_type":"audio","duration":"2"}]}', "")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(audio_processing_service.subprocess, "run", fake_run)

    with pytest.raises(AudioProcessingError, match="convertir"):
        process_audio_copy(source, "referencias")

    assert source.read_bytes() == b"original"
    assert not list((tmp_path / "storage").rglob("*.wav"))
