"""Safe, bounded LaTeX compilation for the collaboration workbench.

The compiler deliberately treats a TeX entrypoint as untrusted input.  It only
reads approved repository roots and writes to a per-job runtime directory.  No
shell is ever used; command arguments are assembled from a small allow-list.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional


APPROVED_INPUT_ROOTS = ("paper", "models", "artifacts")
ALLOWED_COMPILERS = ("auto", "tectonic", "latexmk", "xelatex", "lualatex", "pdflatex")
ALLOWED_ENGINES = ("auto", "xelatex", "lualatex", "pdflatex")
MAX_JOB_ID_LENGTH = 80
DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024


class CompileInputError(ValueError):
    """Raised when a compile request escapes the declared input boundary."""


@dataclass(frozen=True)
class CompilerConfig:
    root: Path
    build_root: Path
    timeout_seconds: int = 120
    max_log_bytes: int = 200_000
    max_pdf_bytes: int = DEFAULT_MAX_PDF_BYTES


@dataclass(frozen=True)
class ToolchainReport:
    available: bool
    status: str
    compiler: Optional[str]
    engine: Optional[str]
    executable: Optional[str]
    candidates: tuple[str, ...] = ()
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = list(self.candidates)
        return payload


@dataclass(frozen=True)
class CompileResult:
    job_id: str
    status: str
    entrypoint: str
    compiler: Optional[str]
    engine: Optional[str]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    log_tail: str = ""
    pdf_path: Optional[str] = None
    pdf_sha256: Optional[str] = None
    pdf_pages: Optional[int] = None
    pdf_bytes: Optional[int] = None
    error_code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _bounded_text(value: Any, max_bytes: int) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= max_bytes:
        return text
    return raw[-max_bytes:].decode("utf-8", errors="replace")


class LatexCompiler:
    """A deterministic compiler facade with an explicit filesystem boundary."""

    def __init__(self, config: CompilerConfig):
        self.config = CompilerConfig(
            root=Path(config.root).resolve(),
            build_root=Path(config.build_root).resolve(),
            timeout_seconds=max(1, int(config.timeout_seconds)),
            max_log_bytes=max(1, int(config.max_log_bytes)),
            max_pdf_bytes=max(1024, int(config.max_pdf_bytes)),
        )
        self.config.build_root.mkdir(parents=True, exist_ok=True)

    def _candidate_toolchains(self) -> Iterable[tuple[str, str, tuple[str, ...]]]:
        # tectonic is the most hermetic option. latexmk/xelatex support the
        # Chinese XeLaTeX workflow used by the paper templates.
        yield "tectonic", "tectonic", ("tectonic",)
        yield "latexmk", "xelatex", ("latexmk",)
        yield "xelatex", "xelatex", ("xelatex",)
        yield "lualatex", "lualatex", ("lualatex",)
        yield "pdflatex", "pdflatex", ("pdflatex",)

    def detect_toolchain(self) -> ToolchainReport:
        candidates: list[str] = []
        for compiler_name, engine_name, executable_names in self._candidate_toolchains():
            for executable_name in executable_names:
                executable = shutil.which(executable_name)
                if executable:
                    candidates.append(compiler_name)
                    if not self._probe_executable(executable):
                        continue
                    return ToolchainReport(
                        available=True,
                        status="AVAILABLE",
                        compiler=compiler_name,
                        engine=engine_name,
                        executable=executable,
                        candidates=tuple(candidates),
                    )
        return ToolchainReport(
            available=False,
            status="UNAVAILABLE",
            compiler=None,
            engine=None,
            executable=None,
            candidates=tuple(candidates),
            reason=(
                "发现候选可执行文件，但均未通过 --version 探测。"
                if candidates
                else "未发现 tectonic、latexmk、xelatex、lualatex 或 pdflatex。"
            ),
        )

    def _probe_executable(self, executable: str) -> bool:
        """Reject PATH entries that cannot start successfully (e.g. latexmk without Perl)."""
        try:
            result = subprocess.run(
                [executable, "--version"],
                cwd=self.config.root,
                shell=False,
                capture_output=True,
                timeout=min(self.config.timeout_seconds, 10),
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def validate_entrypoint(self, entrypoint: str) -> Path:
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            raise CompileInputError("INVALID_ENTRYPOINT")
        candidate_text = entrypoint.replace("\\", "/").strip()
        # PurePosixPath keeps validation platform-neutral, while rejecting
        # Windows drive letters and rooted paths before Path.resolve().
        pure = PurePosixPath(candidate_text)
        if pure.is_absolute() or re.match(r"^[A-Za-z]:", candidate_text):
            raise CompileInputError("INVALID_ENTRYPOINT")
        if any(part in ("", ".", "..") for part in pure.parts):
            raise CompileInputError("INVALID_ENTRYPOINT")
        if pure.suffix.lower() != ".tex":
            raise CompileInputError("INVALID_ENTRYPOINT")
        if not pure.parts or pure.parts[0] not in APPROVED_INPUT_ROOTS:
            raise CompileInputError("INVALID_ENTRYPOINT")
        resolved_root = self.config.root.resolve()
        unresolved = resolved_root.joinpath(*pure.parts)
        current = resolved_root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise CompileInputError("INVALID_ENTRYPOINT")
        resolved = unresolved.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise CompileInputError("INVALID_ENTRYPOINT") from exc
        if not resolved.is_file():
            raise CompileInputError("ENTRYPOINT_NOT_FOUND")
        return resolved

    def _resolve_toolchain(self, compiler: str, engine: str) -> tuple[str, str, str]:
        if compiler not in ALLOWED_COMPILERS:
            raise CompileInputError("INVALID_COMPILER")
        if engine not in ALLOWED_ENGINES:
            raise CompileInputError("INVALID_ENGINE")
        if compiler == "auto":
            detected = self.detect_toolchain()
            if not detected.available or not detected.compiler or not detected.engine or not detected.executable:
                raise CompileInputError("TOOLCHAIN_UNAVAILABLE")
            return detected.compiler, detected.engine, detected.executable
        if compiler == "tectonic":
            executable = shutil.which("tectonic")
            selected_engine = engine if engine != "auto" else "xelatex"
        elif compiler == "latexmk":
            executable = shutil.which("latexmk")
            selected_engine = engine if engine != "auto" else "xelatex"
        else:
            executable = shutil.which(compiler)
            selected_engine = compiler
            if engine not in ("auto", compiler):
                raise CompileInputError("ENGINE_COMPILER_MISMATCH")
        if not executable or not self._probe_executable(executable):
            raise CompileInputError("TOOLCHAIN_UNAVAILABLE")
        return compiler, selected_engine, executable

    def _argv(self, compiler: str, engine: str, executable: str, source: Path, output_dir: Path) -> list[str]:
        if compiler == "tectonic":
            return [executable, "--keep-logs", "--outdir", str(output_dir), str(source)]
        if compiler == "latexmk":
            engine_flag = {"xelatex": "-xelatex", "lualatex": "-lualatex", "pdflatex": "-pdf"}[engine]
            return [
                executable,
                engine_flag,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-latexoption=-no-shell-escape",
                f"-outdir={output_dir}",
                str(source),
            ]
        return [
            executable,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-no-shell-escape",
            "-output-directory",
            str(output_dir),
            str(source),
        ]

    def _pdf_metadata(self, pdf_path: Path) -> tuple[Optional[int], Optional[int]]:
        pages: Optional[int] = None
        size = pdf_path.stat().st_size
        pdfinfo = shutil.which("pdfinfo")
        if not pdfinfo:
            return pages, size
        try:
            completed = subprocess.run(
                [pdfinfo, str(pdf_path)],
                cwd=self.config.root,
                shell=False,
                capture_output=True,
                timeout=min(self.config.timeout_seconds, 10),
                check=False,
            )
            output = _bounded_text(completed.stdout, 20_000)
            match = re.search(r"^Pages:\s*(\d+)\s*$", output, flags=re.MULTILINE)
            if match:
                pages = int(match.group(1))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return pages, size

    def _redact_log(self, value: Any, *, executable: Optional[str] = None) -> str:
        text = _bounded_text(value, self.config.max_log_bytes)

        def path_pattern(raw_path: Path | str) -> str:
            """Build a separator- and TeX-wrap-tolerant path expression.

            MiKTeX/XeLaTeX may wrap a long diagnostic path at an arbitrary
            column and can mix ``\\`` and ``/`` separators.  Matching the
            path component-by-component and allowing a line break between
            characters keeps the redaction useful without exposing the
            configured repository/runtime roots.
            """
            parts = [part for part in re.split(r"[\\/]+", str(raw_path)) if part]
            if not parts:
                return ""
            components: list[str] = []
            for part in parts:
                # Permit a TeX line-wrap after any character in a component.
                wrapped = "".join(re.escape(char) + r"(?:[\r\n][ \t]*)?" for char in part)
                components.append(wrapped)
            # A wrap can replace the separator itself, hence newline is a
            # valid separator in addition to either Windows/POSIX slash.
            return r"(?:[\\/\r\n]+[ \t]*)".join(components)

        def redact_path(raw_path: Path | str, replacement: str) -> None:
            nonlocal text
            pattern = path_pattern(raw_path)
            if pattern:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        redact_path(self.config.root, "<repo>")
        redact_path(self.config.build_root, "<runtime>")
        if executable:
            redact_path(executable, "<tex-engine>")
        return _bounded_text(text, self.config.max_log_bytes)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _new_job_id(self) -> str:
        return f"latex-{int(time.time())}-{uuid.uuid4().hex[:12]}"

    def compile_tex(
        self,
        entrypoint: str,
        *,
        compiler: str = "auto",
        engine: str = "auto",
        job_id: Optional[str] = None,
        clean: bool = True,
    ) -> CompileResult:
        job_id = job_id or self._new_job_id()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", job_id) or len(job_id) > MAX_JOB_ID_LENGTH:
            raise CompileInputError("INVALID_JOB_ID")
        started = _utc_now()
        started_clock = time.monotonic()
        try:
            source = self.validate_entrypoint(entrypoint)
            selected_compiler, selected_engine, executable = self._resolve_toolchain(compiler, engine)
        except CompileInputError as exc:
            code = str(exc)
            status = "FAILED" if code == "ENTRYPOINT_NOT_FOUND" else "UNAVAILABLE" if code == "TOOLCHAIN_UNAVAILABLE" else "FAILED"
            return CompileResult(
                job_id=job_id,
                status=status,
                entrypoint=entrypoint,
                compiler=None if code == "TOOLCHAIN_UNAVAILABLE" else compiler,
                engine=None if code == "TOOLCHAIN_UNAVAILABLE" else engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                error_code=code,
            )

        output_dir = self.config.build_root / job_id
        if clean and output_dir.exists():
            for child in output_dir.iterdir():
                if child.is_file() or child.is_symlink():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
        output_dir.mkdir(parents=True, exist_ok=True)
        argv = self._argv(selected_compiler, selected_engine, executable, source, output_dir)
        try:
            # Redirect process output to a temporary file instead of allowing
            # an unbounded stdout/stderr buffer in the API worker.  Only the
            # bounded tail is read back into the result/event projection.
            with tempfile.TemporaryFile(mode="w+b") as output_stream:
                completed = subprocess.run(
                    argv,
                    cwd=self.config.root,
                    shell=False,
                    stdout=output_stream,
                    stderr=subprocess.STDOUT,
                    timeout=self.config.timeout_seconds,
                    check=False,
                )
                output_stream.seek(0, os.SEEK_END)
                output_stream.seek(max(0, output_stream.tell() - self.config.max_log_bytes))
                bounded_output = output_stream.read()
        except subprocess.TimeoutExpired as exc:
            timeout_log = _bounded_text(getattr(exc, "stdout", "") or "", self.config.max_log_bytes)
            timeout_log += _bounded_text(getattr(exc, "stderr", "") or "", self.config.max_log_bytes)
            log = self._redact_log(timeout_log, executable=executable)
            (output_dir / "compile.log").write_text(log, encoding="utf-8", errors="replace")
            return CompileResult(
                job_id=job_id,
                status="TIMED_OUT",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=log,
                error_code="TIMEOUT",
            )
        except OSError as exc:
            return CompileResult(
                job_id=job_id,
                status="FAILED",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=self._redact_log(str(exc), executable=executable),
                error_code="PROCESS_START_FAILED",
            )

        # Test doubles may return stdout directly; real processes use the
        # redirected bounded tail above.
        fallback_output = (getattr(completed, "stdout", b"") or b"") + (getattr(completed, "stderr", b"") or b"")
        log = self._redact_log(bounded_output or fallback_output, executable=executable)
        (output_dir / "compile.log").write_text(log, encoding="utf-8", errors="replace")
        pdf_path = output_dir / f"{source.stem}.pdf"
        if completed.returncode != 0 or not pdf_path.is_file():
            code = "COMPILER_FAILED" if completed.returncode != 0 else "PDF_NOT_GENERATED"
            return CompileResult(
                job_id=job_id,
                status="FAILED",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=log,
                error_code=code,
            )

        # The compiler must not be able to turn the PDF output into a symlink
        # to an arbitrary host file. Validate both the link and the lightweight
        # PDF signature before hashing or serving it.
        if pdf_path.is_symlink() or pdf_path.resolve().parent != output_dir.resolve():
            return CompileResult(
                job_id=job_id,
                status="FAILED",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=log,
                error_code="INVALID_PDF_OUTPUT",
            )

        pdf_size = pdf_path.stat().st_size
        if pdf_size > self.config.max_pdf_bytes:
            return CompileResult(
                job_id=job_id,
                status="FAILED",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=log,
                error_code="PDF_TOO_LARGE",
            )

        with pdf_path.open("rb") as pdf_stream:
            header = pdf_stream.read(5)
            pdf_stream.seek(max(0, pdf_size - 2048))
            trailer = pdf_stream.read(2048)
        if header != b"%PDF-" or b"%%EOF" not in trailer:
            return CompileResult(
                job_id=job_id,
                status="FAILED",
                entrypoint=entrypoint,
                compiler=selected_compiler,
                engine=selected_engine,
                started_at=started,
                finished_at=_utc_now(),
                duration_ms=int((time.monotonic() - started_clock) * 1000),
                log_tail=log,
                error_code="INVALID_PDF_OUTPUT",
            )

        digest = self._sha256_file(pdf_path)
        pages, size = self._pdf_metadata(pdf_path)
        return CompileResult(
            job_id=job_id,
            status="SUCCEEDED",
            entrypoint=entrypoint,
            compiler=selected_compiler,
            engine=selected_engine,
            started_at=started,
            finished_at=_utc_now(),
            duration_ms=int((time.monotonic() - started_clock) * 1000),
            log_tail=log,
            pdf_path=f"{job_id}/{pdf_path.name}",
            pdf_sha256=f"sha256:{digest}",
            pdf_pages=pages,
            pdf_bytes=size,
        )

    def resolve_pdf(self, job_id: str, relative_path: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", job_id):
            raise CompileInputError("INVALID_JOB_ID")
        pure = PurePosixPath(str(relative_path).replace("\\", "/"))
        if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts) or pure.suffix.lower() != ".pdf":
            raise CompileInputError("INVALID_PDF_PATH")
        expected_root = (self.config.build_root / job_id).resolve()
        resolved = (self.config.build_root / Path(*pure.parts)).resolve()
        try:
            resolved.relative_to(expected_root)
        except ValueError as exc:
            raise CompileInputError("INVALID_PDF_PATH") from exc
        if not resolved.is_file():
            raise CompileInputError("PDF_NOT_FOUND")
        current = self.config.build_root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise CompileInputError("INVALID_PDF_PATH")
        return resolved

    def cleanup_job(self, job_id: str) -> None:
        """Remove one generated job directory after the bounded history expires."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", job_id):
            raise CompileInputError("INVALID_JOB_ID")
        target = (self.config.build_root / job_id).resolve()
        try:
            target.relative_to(self.config.build_root)
        except ValueError as exc:
            raise CompileInputError("INVALID_JOB_ID") from exc
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
