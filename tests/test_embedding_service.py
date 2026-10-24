import json
import subprocess
from pathlib import Path

import pytest

from backend.core.config import settings
from backend.services import embedding_service
from backend.services.embedding_service import (
    EXPECTED_EMBEDDING_DIMENSION,
    EmbeddingError,
    deserialize_embedding,
    generate_embedding,
    get_model,
    serialize_embedding,
)


@pytest.fixture(scope="module")
def normalized_wav(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("embedding") / "normalized.wav"
    subprocess.run(
        [
            settings.ffmpeg_binary,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=2",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_model_loads_once() -> None:
    first = get_model()
    second = get_model()

    assert first is second
    assert Path(settings.speechbrain_model_dir).is_dir()


def test_generate_embedding_has_expected_dimension_and_finite_values(normalized_wav: Path) -> None:
    vector = generate_embedding(normalized_wav)

    assert len(vector) == EXPECTED_EMBEDDING_DIMENSION
    assert all(value == value and abs(value) != float("inf") for value in vector)


def test_embedding_serialization_round_trip() -> None:
    vector = [float(index) / 10 for index in range(EXPECTED_EMBEDDING_DIMENSION)]

    restored = deserialize_embedding(serialize_embedding(vector))

    assert restored == vector
    assert isinstance(json.loads(serialize_embedding(vector)), list)


def test_invalid_embedding_values_are_rejected() -> None:
    with pytest.raises(EmbeddingError):
        serialize_embedding([0.0] * (EXPECTED_EMBEDDING_DIMENSION - 1))
    with pytest.raises(EmbeddingError):
        serialize_embedding([float("nan")] * EXPECTED_EMBEDDING_DIMENSION)


def test_missing_wav_is_rejected() -> None:
    with pytest.raises(FileNotFoundError):
        generate_embedding("missing-normalized.wav")


def test_invalid_audio_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not-a-wav")

    with pytest.raises(EmbeddingError):
        generate_embedding(invalid)


def test_non_normalized_audio_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "stereo.wav"
    subprocess.run(
        [
            settings.ffmpeg_binary,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=1",
            "-ac",
            "2",
            "-ar",
            "8000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(invalid),
        ],
        check=True,
        capture_output=True,
    )

    with pytest.raises(EmbeddingError, match="mono.*16000"):
        generate_embedding(invalid)
