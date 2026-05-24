"""Tests for the ``cbsrm reports`` CLI catalog command.

The command is a thin pass-through over
:func:`cbsrm.reporting.get_report_catalog`. These tests pin the
externally observable CLI contract:

  * exit codes
  * JSON output shape
  * presence of the canonical ``crisis-dossier`` registry entry
  * the command does **not** execute any report
  * argparse rejects unknown subcommand arguments cleanly
  * ``cbsrm reports --help`` works
  * deterministic output (same args → byte-identical stdout)

Methodology and registry internals are covered by
``tests/test_report_registry.py``; this file does not re-validate them.
"""
from __future__ import annotations

import json

import pytest

from cbsrm.cli import main
from cbsrm.reporting import get_report_catalog


# ─── helpers ─────────────────────────────────────────────────────────


def _run(argv, capsys):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# ─── exit code + JSON shape ──────────────────────────────────────────


def test_reports_exits_zero(capsys):
    rc, _out, err = _run(["reports"], capsys)
    assert rc == 0, err
    assert err == ""


def test_reports_stdout_is_valid_json(capsys):
    rc, out, _err = _run(["reports"], capsys)
    assert rc == 0
    # Must parse without raising — the load itself is the assertion.
    json.loads(out)


def test_reports_has_top_level_reports_key(capsys):
    rc, out, _err = _run(["reports"], capsys)
    assert rc == 0
    payload = json.loads(out)
    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"reports"}
    assert isinstance(payload["reports"], list)


def test_reports_contains_crisis_dossier(capsys):
    rc, out, _err = _run(["reports"], capsys)
    assert rc == 0
    payload = json.loads(out)
    ids = [entry["id"] for entry in payload["reports"]]
    assert "crisis-dossier" in ids


def test_reports_output_equals_registry_catalog(capsys):
    """CLI must be a pure pass-through — the parsed JSON equals the
    python-level catalog object."""
    rc, out, _err = _run(["reports"], capsys)
    assert rc == 0
    payload = json.loads(out)
    assert payload == get_report_catalog()


# ─── no execution side effects ──────────────────────────────────────


def test_reports_does_not_build_a_dossier(monkeypatch, capsys):
    """``cbsrm reports`` must NOT invoke ``build_crisis_dossier``.
    The catalog is metadata-only; if the CLI ever drifted into
    executing a report from this surface, this test would fail loudly.
    """
    import cbsrm.diagnostics as diagnostics_pkg

    def _no_build(*_a, **_kw):  # pragma: no cover - defensive
        raise AssertionError(
            "`cbsrm reports` must not call build_crisis_dossier"
        )

    monkeypatch.setattr(
        diagnostics_pkg, "build_crisis_dossier", _no_build
    )

    rc, out, _err = _run(["reports"], capsys)
    assert rc == 0
    payload = json.loads(out)
    assert "crisis-dossier" in [e["id"] for e in payload["reports"]]


# ─── argparse contracts ────────────────────────────────────────────


def test_reports_help_runs(capsys):
    """``cbsrm reports --help`` exits 0 and prints something useful.
    argparse exits via SystemExit when --help is given, so wrap it.
    """
    with pytest.raises(SystemExit) as excinfo:
        main(["reports", "--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "reports" in out
    # Help text should mention the command's pure-metadata nature so
    # callers do not expect a report to be executed by `cbsrm reports`.
    assert "catalog" in out.lower()


def test_reports_rejects_unknown_argument(capsys):
    """argparse should reject unexpected positional args with a
    non-zero exit and an error on stderr, never a traceback."""
    with pytest.raises(SystemExit) as excinfo:
        main(["reports", "extra-arg-not-supported"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert err  # something printed on stderr
    assert "Traceback" not in err


# ─── determinism ────────────────────────────────────────────────────


def test_reports_output_is_byte_identical_across_runs(capsys):
    """Two CLI invocations must produce byte-identical stdout."""
    rc1, out1, _ = _run(["reports"], capsys)
    rc2, out2, _ = _run(["reports"], capsys)
    assert rc1 == 0 and rc2 == 0
    assert out1 == out2
