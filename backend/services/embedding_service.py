import json
from pathlib import Path
from threading import Lock

import torch
import torchaudio
from speechbrain.inference.classifiers import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

from backend.core.config import settings

EXPECTED_EMBEDDING_DIMENSION = 192
MODEL_SOURCE = settings.speechbrain_model_source
_model: EncoderClassifier | None = None
_model_lock = Lock()


class EmbeddingError(ValueError):
    pass


def _load_model() -> EncoderClassifier:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                model_dir = Path(settings.speechbrain_model_dir)
                model_dir.mkdir(parents=True, exist_ok=True)
                _model = EncoderClassifier.from_hparams(
                    source=MODEL_SOURCE,
                    savedir=str(model_dir),
                    local_strategy=LocalStrategy.COPY,
                    run_opts={"device": "cpu"},
                )
    return _model


def get_model() -> EncoderClassifier:
    return _load_model()


def _load_normalized_wav(path: Path) -> torch.Tensor:
    if not path.is_file():
        raise FileNotFoundError(f"No existe el WAV normalizado: {path}")
    try:
        waveform, sample_rate = torchaudio.load(str(path))
    except (OSError, RuntimeError) as error:
        raise EmbeddingError("No se pudo leer el WAV normalizado") from error
    if sample_rate != 16000 or waveform.ndim != 2 or waveform.shape[0] != 1:
        raise EmbeddingError("El WAV debe ser mono y estar muestreado a 16000 Hz")
    if waveform.shape[1] == 0:
        raise EmbeddingError("El WAV no contiene muestras de audio")
    return waveform


def generate_embedding(path: str | Path) -> list[float]:
    waveform = _load_normalized_wav(Path(path))
    model = _load_model()
    with torch.inference_mode():
        embedding = model.encode_batch(waveform)
    vector = embedding.squeeze().detach().cpu().tolist()
    if not isinstance(vector, list) or len(vector) != EXPECTED_EMBEDDING_DIMENSION:
        raise EmbeddingError("La dimensión del embedding no coincide con 192")
    if not all(torch.isfinite(torch.tensor(value)) for value in vector):
        raise EmbeddingError("El embedding contiene valores no finitos")
    return [float(value) for value in vector]


def serialize_embedding(vector: list[float]) -> str:
    values = [float(value) for value in vector]
    if len(values) != EXPECTED_EMBEDDING_DIMENSION:
        raise EmbeddingError("La dimensión del embedding no coincide con 192")
    if not all(torch.isfinite(torch.tensor(value)) for value in values):
        raise EmbeddingError("El embedding contiene valores no finitos")
    return json.dumps(values, separators=(",", ":"), allow_nan=False)


def deserialize_embedding(serialized: str) -> list[float]:
    try:
        vector = json.loads(serialized)
    except json.JSONDecodeError as error:
        raise EmbeddingError("El vector serializado no es JSON válido") from error
    if not isinstance(vector, list):
        raise EmbeddingError("El vector serializado debe ser una lista")
    return [float(value) for value in json.loads(serialize_embedding(vector))]