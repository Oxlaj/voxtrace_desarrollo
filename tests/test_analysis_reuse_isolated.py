"""Run with python -B -m unittest tests.test_analysis_reuse_isolated.

Load service definitions with explicit dependency doubles: no application imports,
settings loading, PostgreSQL, FFmpeg, model downloads or third-party dependencies.
"""
import ast
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import logging

ROOT = Path(__file__).resolve().parents[1]


def load_definitions(relative_path, dependencies):
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    namespace = {"__file__": str(path), "__name__": "isolated_service", **dependencies}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace


class UploadDouble:
    def __init__(self, file, filename):
        self.file, self.filename, self.content_type = file, filename, None

    async def read(self, size):
        return self.file.read(size)

    async def close(self):
        self.file.close()


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class DatabaseError(Exception):
    pass


class IntegrityError(DatabaseError):
    pass


class EmbeddingError(ValueError):
    pass


class Model(SimpleNamespace):
    id_audio = hash_archivo = id_persona = identificador = ruta_archivo = id_analisis = ruta_audio_consulta = MagicMock()


class CopyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        # The helper deliberately confines storage to the project storage tree.
        self.settings = SimpleNamespace(storage_root=str(ROOT / "storage" / f"test-{uuid4().hex}"), max_audio_size_mb=1)
        self.storage = Path(self.settings.storage_root)
        self.addCleanup(self.cleanup_storage)
        self.namespace = load_definitions("backend/services/audio_service.py", {
            "dataclass": dataclass, "sha256": sha256, "compare_digest": compare_digest,
            "Path": Path, "uuid4": uuid4, "UploadFile": UploadDouble, "settings": self.settings,
        })
        self.source = self.storage / "consultas/originales/query.wav"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"synthetic-audio")

    def cleanup_storage(self):
        import shutil
        if self.storage.exists():
            shutil.rmtree(self.storage)

    async def copy(self, **overrides):
        args = dict(source_path=str(self.source), original_name="consulta.wav", original_format="wav", expected_hash=sha256(b"synthetic-audio").hexdigest())
        args.update(overrides)
        return await self.namespace["copy_analysis_original"](**args)

    async def test_copy_preserves_query_and_uses_uuid_and_hash(self):
        stored = await self.copy()
        self.assertEqual(stored.path.read_bytes(), self.source.read_bytes())
        self.assertEqual(self.source.read_bytes(), b"synthetic-audio")
        self.assertEqual(stored.sha256, sha256(b"synthetic-audio").hexdigest())
        self.assertEqual(stored.path.parent, self.storage / "referencias/originales")
        self.assertEqual(len(stored.path.stem), 32)
        self.assertEqual(stored.original_name, "consulta.wav")

    async def test_changed_hash_removes_only_new_copy(self):
        with self.assertRaises(ValueError):
            await self.copy(expected_hash="a" * 64)
        self.assertEqual(list(self.storage.glob("referencias/originales/*")), [])
        self.assertTrue(self.source.exists())

    async def test_outside_query_directory_is_rejected(self):
        outside = Path(self.temp.name) / "outside.wav"
        outside.write_bytes(b"synthetic-audio")
        with self.assertRaises(ValueError):
            await self.copy(source_path=str(outside))
        self.assertTrue(outside.exists())

    async def test_missing_original_and_wrong_format_are_rejected(self):
        with self.assertRaises(ValueError):
            await self.copy(original_format="mp3")
        self.source.unlink()
        with self.assertRaises(ValueError):
            await self.copy()

    async def test_size_limit_removes_copy_and_preserves_original(self):
        self.settings.max_audio_size_mb = 0
        with self.assertRaises(ValueError):
            await self.copy()
        self.assertTrue(self.source.exists())
        self.assertEqual(list(self.storage.glob("referencias/originales/*")), [])

    async def test_external_storage_is_rejected_without_writing(self):
        self.settings.storage_root = self.temp.name
        with self.assertRaises(ValueError):
            await self.copy()
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    async def test_invalid_hash_is_rejected_before_creating_copy(self):
        with self.assertRaises(ValueError):
            await self.copy(expected_hash="valor inválido")
        self.assertFalse((self.storage / "referencias").exists())


class ReuseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.original = Path(self.temp.name) / "query.wav"
        self.copy_path = Path(self.temp.name) / "copy.wav"
        self.processed = Path(self.temp.name) / "processed.wav"
        for path in (self.original, self.copy_path, self.processed):
            path.write_bytes(b"synthetic")
        self.analysis = SimpleNamespace(estado="completado", ruta_audio_consulta=str(self.original), nombre_original="consulta.wav", formato_original="wav", hash_audio_consulta="a" * 64)
        self.person = Model(id_persona=3)
        self.db = MagicMock()
        self.db.get.side_effect = [self.analysis, self.person]
        self.db.scalar.return_value = None
        self.copy = AsyncMock(return_value=SimpleNamespace(path=self.copy_path, original_name="consulta.wav", extension="wav", sha256="a" * 64))
        self.process = MagicMock(return_value=SimpleNamespace(processed_path=self.processed, duration_seconds=2))
        self.audit = MagicMock()
        self.namespace = load_definitions("backend/services/analysis_reuse_service.py", {
            "logging": logging, "HTTPException": HTTPError, "Request": object,
            "Session": object, "Usuario": Model, "Analisis": Model, "Audio": Model,
            "Persona": Model, "Embedding": Model, "ReutilizarAudioRequest": object,
            "ReutilizarAudioResponse": SimpleNamespace, "settings": SimpleNamespace(speechbrain_model_source="test-model"),
            "select": MagicMock(), "or_": MagicMock(), "IntegrityError": IntegrityError, "SQLAlchemyError": DatabaseError,
            "copy_analysis_original": self.copy, "process_audio_copy": self.process,
            "AudioProcessingError": ValueError, "EmbeddingError": EmbeddingError, "generate_embedding": MagicMock(return_value=[0.1]),
            "serialize_embedding": MagicMock(return_value="[0.1]"), "add_event": self.audit,
            "record_event": MagicMock(), "PERSON_CREATED": "persona_creada", "SAMPLE_ERROR": "error_muestra",
        })
        self.user = Model(id_usuario=7, rol=SimpleNamespace(nombre="Investigador"), debe_cambiar_password=False)
        self.payload = SimpleNamespace(confirmar=True, id_persona=3, nueva_persona=None)

        def assign_ids():
            for call in self.db.add.call_args_list:
                item = call.args[0]
                if "ruta_archivo" in vars(item):
                    item.id_audio = 11
                elif "nombre" in vars(item):
                    item.id_persona = 9
        self.db.flush.side_effect = assign_ids

    async def reuse(self):
        return await self.namespace["reuse_analysis_audio"](5, self.payload, object(), self.db, self.user)

    async def test_existing_person_commits_sample_embedding_and_audit_once(self):
        response = await self.reuse()
        self.assertEqual((response.id_analisis, response.id_persona, response.id_audio), (5, 3, 11))
        self.db.commit.assert_called_once()
        self.assertEqual(len(self.db.add.call_args_list), 2)
        self.assertIn("confirmacion_explicita", self.audit.call_args.args[-1])
        self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())
        self.assertFalse(hasattr(response, "ruta_archivo"))

    async def test_new_person_and_sample_are_atomic(self):
        self.db.get.side_effect = [self.analysis]
        self.payload.nueva_persona = SimpleNamespace(identificador="P-9", model_dump=lambda: {"identificador": "P-9", "nombre": "Persona sintética"})
        self.payload.id_persona = None
        response = await self.reuse()
        self.assertEqual(response.id_persona, 9)
        self.db.commit.assert_called_once()
        self.assertEqual(self.audit.call_count, 2)

    async def test_analyst_and_pending_password_are_denied_before_file_access(self):
        self.user.rol.nombre = "Analista"
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 403)
        self.user.rol.nombre = "Administrador"
        self.user.debe_cambiar_password = True
        with self.assertRaises(HTTPError):
            await self.reuse()
        self.copy.assert_not_called()
        self.db.get.assert_not_called()

    async def test_confirmation_is_required(self):
        self.payload.confirmar = False
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 422)
        self.copy.assert_not_called()

    async def test_duplicate_is_rejected_before_copy(self):
        self.db.scalar.return_value = 11
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 409)
        self.copy.assert_not_called()

    async def test_commit_integrity_error_preserves_copies_for_review(self):
        self.db.commit.side_effect = IntegrityError()
        with self.assertLogs("isolated_service", level="WARNING") as logs:
            with self.assertRaises(HTTPError) as caught:
                await self.reuse()
        self.assertEqual(caught.exception.status_code, 409)
        self.db.rollback.assert_called()
        self.assertTrue(self.original.exists())
        self.assertTrue(self.copy_path.exists() and self.processed.exists())
        self.assertIn("copias conservadas", " ".join(logs.output))

    async def test_embedding_failure_rolls_back_without_creating_person(self):
        self.namespace["generate_embedding"].side_effect = RuntimeError("synthetic failure")
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 500)
        self.db.add.assert_not_called()
        self.assertTrue(self.original.exists())
        self.assertFalse(self.copy_path.exists() or self.processed.exists())

    async def test_unfinished_analysis_is_rejected(self):
        self.analysis.estado = "error"
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 409)
        self.copy.assert_not_called()

    async def test_missing_analysis_or_person_is_rejected(self):
        for results in ([None], [self.analysis, None]):
            self.db.get.side_effect = results
            with self.assertRaises(HTTPError) as caught:
                await self.reuse()
            self.assertEqual(caught.exception.status_code, 404)
        self.copy.assert_not_called()

    async def test_duplicate_identifier_does_not_create_person_or_copy(self):
        self.payload.nueva_persona = SimpleNamespace(identificador="P-9")
        self.payload.id_persona = None
        self.db.scalar.side_effect = [None, 9]
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 409)
        self.db.add.assert_not_called()
        self.copy.assert_not_called()

    async def test_embedding_error_matches_upload_contract(self):
        self.namespace["generate_embedding"].side_effect = EmbeddingError("synthetic failure")
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "No se pudo generar la representación biométrica")
        self.db.commit.assert_not_called()
        self.assertTrue(self.original.exists())
        self.assertFalse(self.copy_path.exists() or self.processed.exists())

    async def test_flush_failure_before_commit_cleans_confirmed_unreferenced_copies(self):
        self.db.flush.side_effect = IntegrityError()
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 409)
        self.db.commit.assert_not_called()
        self.assertTrue(self.original.exists())
        self.assertFalse(self.copy_path.exists() or self.processed.exists())
        self.assertEqual(self.db.scalar.call_count, 3)  # duplicate, audio ref, query ref

    async def test_lost_commit_reply_preserves_possibly_persisted_files(self):
        persisted = []

        def server_committed_but_reply_lost():
            persisted.extend(call.args[0] for call in self.db.add.call_args_list)
            raise DatabaseError("commit acknowledgement lost")

        self.db.commit.side_effect = server_committed_but_reply_lost
        with self.assertLogs("isolated_service", level="WARNING") as logs:
            with self.assertRaises(HTTPError) as caught:
                await self.reuse()
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(len(persisted), 2)
        self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())
        self.assertIn("copias conservadas", " ".join(logs.output))
        self.assertEqual(self.db.scalar.call_count, 1)  # never use lookup to justify uncertain commit cleanup

    async def test_failure_delivering_response_after_successful_commit_preserves_files(self):
        with self.assertRaises(ConnectionError):
            await self.reuse()
            raise ConnectionError("client disconnected after commit")
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()
        self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())

    async def test_rollback_failure_preserves_files_and_original_error(self):
        self.namespace["generate_embedding"].side_effect = EmbeddingError("synthetic failure")
        self.db.rollback.side_effect = DatabaseError("rollback failed")
        with self.assertLogs("isolated_service", level="WARNING"):
            with self.assertRaises(HTTPError) as caught:
                await self.reuse()
        self.assertEqual(caught.exception.detail, "No se pudo generar la representación biométrica")
        self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())
        self.namespace["record_event"].assert_not_called()

    async def test_reference_lookup_failure_preserves_files(self):
        self.namespace["generate_embedding"].side_effect = EmbeddingError("synthetic failure")
        self.db.scalar.side_effect = [None, DatabaseError("lookup unavailable")]
        with self.assertLogs("isolated_service", level="WARNING") as logs:
            with self.assertRaises(HTTPError):
                await self.reuse()
        self.assertIn("ausencia de referencias", " ".join(logs.output))
        self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())

    async def test_existing_reference_preserves_both_copies(self):
        for audio_ref, query_ref in ((11, None), (None, 5)):
            self.db.get.side_effect = [self.analysis, self.person]
            self.db.scalar.side_effect = [None, audio_ref, query_ref]
            self.namespace["generate_embedding"].side_effect = EmbeddingError("synthetic failure")
            with self.assertLogs("isolated_service", level="WARNING"):
                with self.assertRaises(HTTPError):
                    await self.reuse()
            self.assertTrue(self.original.exists() and self.copy_path.exists() and self.processed.exists())

    async def test_audit_failure_before_commit_rolls_back_and_cleans(self):
        self.audit.side_effect = DatabaseError("audit insert failed")
        with self.assertRaises(HTTPError) as caught:
            await self.reuse()
        self.assertEqual(caught.exception.status_code, 500)
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called()
        self.assertTrue(self.original.exists())
        self.assertFalse(self.copy_path.exists() or self.processed.exists())

    async def test_administrator_is_authorized(self):
        self.user.rol.nombre = "Administrador"
        response = await self.reuse()
        self.assertEqual(response.id_persona, 3)
        self.db.commit.assert_called_once()

    def test_form_messages_are_utf8(self):
        text = (ROOT / "frontend/static/js/persona-form.js").read_text(encoding="utf-8")
        self.assertIn("análisis", text)
        self.assertIn("confirmación", text)
        self.assertIn("¿Confirma", text)
        self.assertNotIn("an?lisis", text)


if __name__ == "__main__":
    unittest.main()
