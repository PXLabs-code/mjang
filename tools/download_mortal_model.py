"""Download and validate a user-selected Mortal v3/v4 checkpoint."""

import argparse
import hashlib
import os
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Collection, Mapping


_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
_VERSION_NUMBERS = {"v3": 3, "v4": 4}


def verify_checkpoint_version(
    checkpoint: Any,
    requested_version: str,
    runtime_supported_versions: Collection[str],
) -> int:
    if requested_version not in _VERSION_NUMBERS:
        raise ValueError("model version must be v3 or v4")
    if not runtime_supported_versions or any(
        version not in _VERSION_NUMBERS for version in runtime_supported_versions
    ):
        raise ValueError("runtime must declare support for v3 and/or v4")
    if requested_version not in runtime_supported_versions:
        raise ValueError(
            f"model {requested_version} is not supported by runtime "
            f"{', '.join(sorted(runtime_supported_versions))}"
        )
    if not isinstance(checkpoint, Mapping):
        raise ValueError("checkpoint root must be a mapping")

    config = checkpoint.get("config")
    control = config.get("control") if isinstance(config, Mapping) else None
    version = control.get("version") if isinstance(control, Mapping) else None
    expected = _VERSION_NUMBERS[requested_version]
    if type(version) is not int or version != expected:
        raise ValueError(
            f"checkpoint config.control.version is {version!r}; expected {expected}"
        )
    return version


def safe_load_checkpoint(path: Path) -> Any:
    try:
        import torch
    except ImportError as error:
        raise RuntimeError(
            "PyTorch is required to inspect the checkpoint; install a trusted "
            "PyTorch build that matches the selected Mortal runtime"
        ) from error

    return torch.load(path, map_location="cpu", weights_only=True)


def download_checkpoint(
    url: str,
    sha256: str,
    model_version: str,
    runtime_supported_versions: Collection[str],
    output_dir: Path,
    filename: str | None = None,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    checkpoint_loader: Callable[[Path], Any] = safe_load_checkpoint,
) -> Path:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("model URL must use HTTPS")
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise ValueError("SHA-256 must contain exactly 64 hexadecimal characters")
    if model_version not in _VERSION_NUMBERS:
        raise ValueError("model version must be v3 or v4")
    if not runtime_supported_versions or any(
        version not in _VERSION_NUMBERS for version in runtime_supported_versions
    ):
        raise ValueError("runtime must declare support for v3 and/or v4")

    if filename is None:
        filename = Path(urllib.parse.unquote(parsed_url.path)).name
    if not filename or filename in {".", ".."} or Path(filename).name != filename:
        raise ValueError("filename must be a plain file name")

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / filename
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_dir,
            prefix=f".{filename}.",
            suffix=".part",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            digest = hashlib.sha256()
            with opener(url, timeout=60) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    temporary_file.write(chunk)
                    digest.update(chunk)

        if digest.hexdigest().lower() != sha256.lower():
            raise ValueError(
                f"SHA-256 mismatch: expected {sha256.lower()}, got {digest.hexdigest()}"
            )

        checkpoint = checkpoint_loader(temporary_path)
        detected_version = verify_checkpoint_version(
            checkpoint, model_version, runtime_supported_versions
        )
        os.replace(temporary_path, destination)
        temporary_path = None
        print(f"Verified Mortal v{detected_version} checkpoint: {destination}")
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="user-selected HTTPS checkpoint URL")
    parser.add_argument("--sha256", required=True, help="expected checkpoint SHA-256")
    parser.add_argument("--model-version", required=True, choices=("v3", "v4"))
    parser.add_argument(
        "--runtime-supported-versions",
        required=True,
        help="comma-separated versions explicitly supported by this runtime (v3, v4, or both)",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--filename", help="optional destination file name")
    args = parser.parse_args()
    runtime_supported_versions = {
        version.strip() for version in args.runtime_supported_versions.split(",")
    }
    download_checkpoint(
        args.url,
        args.sha256,
        args.model_version,
        runtime_supported_versions,
        args.output_dir,
        args.filename,
    )


if __name__ == "__main__":
    main()
