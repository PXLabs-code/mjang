import hashlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from download_mortal_model import (  # noqa: E402
    download_checkpoint,
    safe_load_checkpoint,
    verify_checkpoint_version,
)


class DownloadMortalModelTests(unittest.TestCase):
    def test_requires_matching_checkpoint_and_runtime_version(self) -> None:
        checkpoint = {"config": {"control": {"version": 4}}}

        self.assertEqual(
            verify_checkpoint_version(checkpoint, "v4", {"v3", "v4"}), 4
        )
        with self.assertRaisesRegex(ValueError, "not supported by runtime"):
            verify_checkpoint_version(checkpoint, "v4", {"v3"})
        with self.assertRaisesRegex(ValueError, "expected 3"):
            verify_checkpoint_version(checkpoint, "v3", {"v3", "v4"})

    def test_loads_checkpoint_with_weights_only_enabled(self) -> None:
        expected = {"config": {"control": {"version": 3}}}
        load = unittest.mock.Mock(return_value=expected)
        fake_torch = types.SimpleNamespace(load=load)

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            sys.modules, {"torch": fake_torch}
        ):
            checkpoint_path = Path(temp_dir) / "model.pth"
            checkpoint_path.write_bytes(b"checkpoint")
            loaded = safe_load_checkpoint(checkpoint_path)

        self.assertIs(loaded, expected)
        load.assert_called_once_with(
            checkpoint_path, map_location="cpu", weights_only=True
        )

    def test_downloads_only_after_hash_and_version_checks(self) -> None:
        content = b"checkpoint bytes"
        expected_hash = hashlib.sha256(content).hexdigest()

        def opener(_url: str, timeout: int) -> io.BytesIO:
            self.assertEqual(timeout, 60)
            return io.BytesIO(content)

        with tempfile.TemporaryDirectory() as temp_dir:
            destination = download_checkpoint(
                "https://models.example/model.pth",
                expected_hash,
                "v4",
                {"v3", "v4"},
                Path(temp_dir),
                checkpoint_loader=lambda _path: {"config": {"control": {"version": 4}}},
                opener=opener,
            )

            self.assertEqual(destination.read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                download_checkpoint(
                    "https://models.example/model.pth",
                    "0" * 64,
                    "v4",
                    {"v3", "v4"},
                    Path(temp_dir),
                    checkpoint_loader=lambda _path: self.fail("loader must not run"),
                    opener=opener,
                )
            self.assertFalse(any(Path(temp_dir).glob("*.part")))

    def test_rejects_non_https_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                download_checkpoint(
                    "http://models.example/model.pth",
                    "0" * 64,
                    "v3",
                    {"v3"},
                    Path(temp_dir),
                )


if __name__ == "__main__":
    unittest.main()
