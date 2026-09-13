"""Thin :mod:`subprocess` wrapper around the ``pandoc`` CLI.

Flags are fixed by ``docs/import-syntax-mapping.md`` §1. We deliberately do
**not** depend on ``pypandoc`` — calling the binary directly is one fewer
abstraction to debug, and the binary is shipped via the Docker image (see
``Dockerfile``).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PANDOC_BINARY = "pandoc"
DEFAULT_TIMEOUT_SECONDS = 60

# Order matches docs/import-syntax-mapping.md §1.
_TO_EXTENSIONS = (
    "markdown_strict",
    "pipe_tables",
    "backtick_code_blocks",
    "tex_math_dollars",
    "raw_tex",
    "bracketed_spans",
)


class PandocError(RuntimeError):
    """Raised when ``pandoc`` is missing, times out, or returns non-zero."""


@dataclass
class PandocRunner:
    """Run ``pandoc`` against a DOCX file and return the produced markdown.

    The runner is cheap to construct; instantiate per call or hold one
    long-lived instance, both work. Configuration via constructor args wins
    over environment variables, which in turn override the defaults.
    """

    binary: str | None = None
    timeout_seconds: int | None = None

    def run(self, docx_path: Path, media_dir: Path) -> str:
        if not docx_path.is_file():
            raise PandocError(f"input docx not found: {docx_path}")
        media_dir.mkdir(parents=True, exist_ok=True)

        binary = self.binary or os.environ.get("PANDOC_BINARY", DEFAULT_PANDOC_BINARY)
        timeout = self.timeout_seconds
        if timeout is None:
            raw = os.environ.get("PANDOC_TIMEOUT_SECONDS")
            timeout = int(raw) if raw else DEFAULT_TIMEOUT_SECONDS

        cmd = [
            binary,
            str(docx_path),
            "--from=docx",
            "--to=" + "+".join(_TO_EXTENSIONS),
            f"--extract-media={media_dir}",
            "--wrap=none",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise PandocError(
                f"pandoc binary not found: {binary!r} "
                "(install pandoc or set PANDOC_BINARY)"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PandocError(
                f"pandoc timed out after {timeout}s on {docx_path}"
            ) from exc

        if proc.returncode != 0:
            raise PandocError(
                f"pandoc exited with code {proc.returncode}: "
                f"{proc.stderr.strip() or proc.stdout.strip() or '<no output>'}"
            )
        return proc.stdout


__all__ = [
    "DEFAULT_PANDOC_BINARY",
    "DEFAULT_TIMEOUT_SECONDS",
    "PandocError",
    "PandocRunner",
]
