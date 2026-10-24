import subprocess
from pathlib import Path

import pytest

from backend.core.config import settings
from backend.services.audio_processing_service import (
    AudioProcessingError,
    _audio_duration,
    process_audio_copy,
)


def make_audio_file(path: Path, duration: float = 2.0) -> None:
    subprocess.run(
        [
            settings.ffmpeg_binary,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def make_video_without_audio(path: Path) -> None:
    subprocess.run(
        [
            settings.ffmpeg_binary,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=1",
            "-an",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_process_audio_creates_wav_mono_16khz_and_preserves_original(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    source = tmp_path / "original.wav"
    make_audio_file(source, duration=61)
    original_bytes = source.read_bytes()

    result = process_audio_copy(source, "referencias")

    assert source.read_bytes() == original_bytes
    assert result.processed_path.parent.name == "procesados"
    assert result.processed_path.suffix == ".wav"
    assert result.duration_seconds >= 60
    probe = subprocess.run(
        [settings.ffprobe_binary, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels,codec_name", "-of", "default=noprint_wrappers=1", str(result.processed_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "sample_rate=16000" in probe
    assert "channels=1" in probe
    assert "codec_name=pcm_s16le" in probe


def test_process_audio_accepts_valid_short_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    source = tmp_path / "short.wav"
    make_audio_file(source, duration=0.2)

    result = process_audio_copy(source, "referencias")

    assert 0 < result.duration_seconds < 60
    assert result.processed_path.is_file()


def test_process_audio_rejects_corrupt_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    source = tmp_path / "corrupt.wav"
    source.write_bytes(b"not-an-audio-file")

    with pytest.raises(AudioProcessingError, match="corrupto"):
        process_audio_copy(source, "referencias")


def test_process_audio_rejects_file_without_audio_stream(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_root", str(tmp_path / "storage"))
    source = tmp_path / "video.mp4"
    make_video_without_audio(source)

    with pytest.raises(AudioProcessingError, match="pista de audio"):
        process_audio_copy(source, "referencias")


def test_zero_duration_remains_invalid() -> None:
    with pytest.raises(AudioProcessingError, match="duración del audio no es válida"):
        _audio_duration({"streams": [{"codec_type": "audio", "duration": "0"}]})
