"""TDD contract tests for the safe LaTeX/PDF compiler boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import latex_compiler as compiler


def make_service(tmp_path: Path) -> compiler.LatexCompiler:
    root = tmp_path / "repo"
    (root / "paper").mkdir(parents=True)
    (root / "paper" / "main.tex").write_text(r"\\documentclass{article}\\begin{document}ok\\end{document}", encoding="utf-8")
    return compiler.LatexCompiler(compiler.CompilerConfig(root=root, build_root=tmp_path / "runtime" / "latex"))


def test_validate_entrypoint_allows_only_repo_tex_roots(tmp_path):
    service = make_service(tmp_path)

    assert service.validate_entrypoint("paper/main.tex") == (tmp_path / "repo" / "paper" / "main.tex").resolve()
    with pytest.raises(compiler.CompileInputError):
        service.validate_entrypoint("../backend/app.py")
    with pytest.raises(compiler.CompileInputError):
        service.validate_entrypoint("paper/notes.md")
    with pytest.raises(compiler.CompileInputError):
        service.validate_entrypoint(str((tmp_path / "repo" / "paper" / "main.tex").resolve()))


def test_toolchain_report_is_explicitly_unavailable_when_no_compiler(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    monkeypatch.setattr(compiler.shutil, "which", lambda _name: None)

    report = service.detect_toolchain()

    assert report.available is False
    assert report.status == "UNAVAILABLE"
    assert report.compiler is None


def test_toolchain_skips_path_entry_that_fails_version_probe(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    paths = {"latexmk": "latexmk.exe", "xelatex": "xelatex.exe"}
    monkeypatch.setattr(compiler.shutil, "which", lambda name: paths.get(name))

    def fake_run(argv, **_kwargs):
        return SimpleNamespace(returncode=1 if argv[0] == "latexmk.exe" else 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(compiler.subprocess, "run", fake_run)

    report = service.detect_toolchain()

    assert report.compiler == "xelatex"
    assert report.engine == "xelatex"


def test_compile_uses_fixed_argv_and_shell_false(monkeypatch, tmp_path):
    service = make_service(tmp_path)
    calls = []

    def fake_which(name):
        return "xelatex.exe" if name == "xelatex" else None

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if "--version" in argv:
            return SimpleNamespace(returncode=0, stdout=b"xelatex", stderr=b"")
        output_dir = Path(argv[argv.index("-output-directory") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
        return SimpleNamespace(returncode=0, stdout=(str(service.config.root) + " compiled").encode(), stderr=b"")

    monkeypatch.setattr(compiler.shutil, "which", fake_which)
    monkeypatch.setattr(compiler.subprocess, "run", fake_run)

    result = service.compile_tex("paper/main.tex", compiler="xelatex", engine="xelatex")

    assert result.status == "SUCCEEDED"
    assert result.pdf_sha256.startswith("sha256:")
    assert calls
    argv, kwargs = calls[-1]
    assert isinstance(argv, list)
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == service.config.root
    assert "-halt-on-error" in argv
    assert str(service.config.root) not in result.log_tail


def test_compile_rejects_malformed_pdf(monkeypatch, tmp_path):
    service = make_service(tmp_path)

    def fake_which(name):
        return "xelatex.exe" if name == "xelatex" else None

    def fake_run(argv, **_kwargs):
        if "--version" in argv:
            return SimpleNamespace(returncode=0, stdout=b"xelatex", stderr=b"")
        output_dir = Path(argv[argv.index("-output-directory") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "main.pdf").write_bytes(b"not-a-pdf")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(compiler.shutil, "which", fake_which)
    monkeypatch.setattr(compiler.subprocess, "run", fake_run)

    result = service.compile_tex("paper/main.tex", compiler="xelatex", engine="xelatex")

    assert result.status == "FAILED"
    assert result.error_code == "INVALID_PDF_OUTPUT"


def test_compile_returns_timed_out_and_bounds_log(monkeypatch, tmp_path):
    service = compiler.LatexCompiler(
        compiler.CompilerConfig(root=tmp_path / "repo", build_root=tmp_path / "runtime", max_log_bytes=100)
    )
    (tmp_path / "repo" / "paper").mkdir(parents=True)
    (tmp_path / "repo" / "paper" / "main.tex").write_text("x", encoding="utf-8")

    monkeypatch.setattr(compiler.shutil, "which", lambda name: "xelatex.exe" if name == "xelatex" else None)

    def fake_timeout(_argv, **_kwargs):
        if "--version" in _argv:
            return SimpleNamespace(returncode=0, stdout=b"xelatex", stderr=b"")
        raise subprocess.TimeoutExpired("xelatex", 1, output=b"o" * 1000, stderr=b"e" * 1000)

    monkeypatch.setattr(compiler.subprocess, "run", fake_timeout)

    result = service.compile_tex("paper/main.tex", compiler="xelatex", engine="xelatex")

    assert result.status == "TIMED_OUT"
    assert result.error_code == "TIMEOUT"
    assert len(result.log_tail.encode("utf-8")) <= 100


def test_compile_missing_entrypoint_fails_closed(tmp_path):
    service = make_service(tmp_path)

    result = service.compile_tex("paper/missing.tex")

    assert result.status == "FAILED"
    assert result.error_code == "ENTRYPOINT_NOT_FOUND"


def test_redact_log_handles_mixed_separators_and_wrapped_components(tmp_path):
    service = make_service(tmp_path)
    # TeX diagnostics can mix Windows/POSIX separators and insert a line
    # break inside a long path component.  The absolute root must still be
    # replaced before the log is exposed through the API.
    mixed = str(service.config.root).replace("\\", "/")
    mixed = mixed.replace("/", "\\", 1)
    mixed = mixed.replace("repo", "re\npo", 1)

    redacted = service._redact_log(f"fatal: {mixed}/paper/main.tex")

    assert "<repo>" in redacted
    assert "re\npo" not in redacted
