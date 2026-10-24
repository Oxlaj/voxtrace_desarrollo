import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from backend.core.config import settings


@dataclass(frozen=True)
class AudioProcessingResult:
    duration_seconds: float
    processed_path: Path


class AudioProcessingError(ValueError):
    pass


def _run_ffprobe(source_path: Path) -> dict:
    command = [
        settings.ffprobe_binary,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type,duration:format=duration",
        "-of",
        "json",
        str(source_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise AudioProcessingError("El archivo de audio es inválido o está corrupto") from error


def _audio_duration(probe_data: dict) -> float:
    streams = probe_data.get("streams", [])
    if not streams or streams[0].get("codec_type") != "audio":
        raise AudioProcessingError("El archivo no contiene una pista de audio")

    stream_duration = streams[0].get("duration")
    format_duration = probe_data.get("format", {}).get("duration")
    raw_duration = stream_duration or format_duration
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError) as error:
        raise AudioProcessingError("No se pudo obtener la duración del audio") from error

    if duration <= 0:
        raise AudioProcessingError("La duración del audio no es válida")
    return duration


def _processed_directory(category: str) -> Path:
    if category not in {"referencias", "consultas"}:
        raise AudioProcessingError("Categoría de procesamiento no permitida")
    directory = Path(settings.storage_root) / category / "procesados"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def process_audio_copy(source_path: Path, category: str) -> AudioProcessingResult:
    probe_data = _run_ffprobe(source_path)
    duration = _audio_duration(probe_data)
    processed_path = _processed_directory(category) / f"{uuid4().hex}.wav"
    command = [
        settings.ffmpeg_binary,
        "-v",
        "error",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(processed_path),
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        if not processed_path.is_file() or processed_path.stat().st_size == 0:
            raise AudioProcessingError("FFmpeg no generó un archivo procesado válido")
    except (OSError, subprocess.CalledProcessError, AudioProcessingError) as error:
        processed_path.unlink(missing_ok=True)
        if isinstance(error, AudioProcessingError):
            raise
        raise AudioProcessingError("No se pudo convertir el audio a WAV") from error

    return AudioProcessingResult(duration_seconds=duration, processed_path=processed_path)
