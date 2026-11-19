import subprocess
from pathlib import Path

import pytest

from src.app import latex

SRC = open("templates/resume.tex").read()


def fake_run_factory(calls, rc=0, stdout="", stderr=""):
    def fake(cmd, cwd=None, **kw):
        calls.append(cmd)
        if rc == 0:
            Path(cwd, "resume.pdf").write_bytes(b"%PDF-fake")
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    return fake


def have(*names):
    return lambda n: f"/usr/bin/{n}" if n in names else None


def test_prefers_tectonic(monkeypatch):
    calls = []
    monkeypatch.setattr(latex.shutil, "which", have("tectonic", "pdflatex"))
    monkeypatch.setattr(latex.subprocess, "run", fake_run_factory(calls))
    assert latex.compile_pdf(SRC).startswith(b"%PDF") and calls[0][0] == "tectonic"


def test_falls_back_to_pdflatex_without_shell_escape(monkeypatch):
    calls = []
    monkeypatch.setattr(latex.shutil, "which", have("pdflatex"))
    monkeypatch.setattr(latex.subprocess, "run", fake_run_factory(calls))
    latex.compile_pdf(SRC)
    assert calls[0][0] == "pdflatex" and "-no-shell-escape" in calls[0]


def test_no_engine_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(latex.shutil, "which", have())
    with pytest.raises(latex.LatexError, match="tectonic or TeX Live"):
        latex.compile_pdf(SRC)


def test_pdflatex_errors_come_from_stdout(monkeypatch):
    monkeypatch.setattr(latex.shutil, "which", have("pdflatex"))
    monkeypatch.setattr(latex.subprocess, "run",
                        fake_run_factory([], rc=1, stdout="! Undefined control sequence."))
    with pytest.raises(latex.LatexError, match="Undefined control sequence"):
        latex.compile_pdf(SRC)
