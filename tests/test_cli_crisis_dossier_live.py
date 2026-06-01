"""
Tests for the ``cbsrm crisis-dossier-live`` CLI command (Block 2 CLI/API).

The command builds its client adapter via the module-level factory
``cbsrm.cli._make_live_clients`` — these tests monkeypatch that factory
with a fake (fed by a fake FRED), so they never touch the network. Covers
each output format, the PDF --output requirement, and the clean failure
path when the live fetch fails with no cache.

Run: pytest tests/test_cli_crisis_dossier_live.py -v
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import cbsrm.cli as cli
from cbsrm.cli import main
from cbsrm.diagnostics import LiveDossierClients


START, END = "2008-09-15", "2008-12-31"


class _FakeFRED:
    def __init__(self, raise_exc: Exception | None = None):
        self._raise = raise_exc

    def get_series(self, series_id, *, observation_start=None,
                   observation_end=None, **_kw):
        if self._raise is not None:
            raise self._raise
        idx = pd.to_datetime(["2008-09-29", "2008-10-15", "2008-11-07"])
        base = 100.0 if series_id == "SP500" else 95.0
        return pd.Series([base, base - 5, base - 12], index=idx, name=series_id)


def _patch_factory(monkeypatch, fred):
    def _fake(network_window: str):
        return LiveDossierClients(fred=fred, network_window=network_window)

    monkeypatch.setattr(cli, "_make_live_clients", _fake)


def _run(argv, capsys):
    rc = main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


# ─── happy paths ───────────────────────────────────────────────────


def test_live_json_output(monkeypatch, capsys):
    _patch_factory(monkeypatch, _FakeFRED())
    rc, out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END], capsys)
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["dossier"]["metadata"]["data_source"] == "live"
    assert "live: data_source=live" in err


def test_live_markdown_output(monkeypatch, capsys):
    _patch_factory(monkeypatch, _FakeFRED())
    rc, out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END,
         "--format", "markdown"], capsys)
    assert rc == 0, err
    assert out.startswith("# ")


def test_live_html_output(monkeypatch, capsys):
    pytest.importorskip("markdown")
    _patch_factory(monkeypatch, _FakeFRED())
    rc, out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END,
         "--format", "html"], capsys)
    assert rc == 0, err
    assert "<!DOCTYPE html>" in out


def test_live_pdf_output(monkeypatch, tmp_path, capsys):
    pytest.importorskip("reportlab")
    _patch_factory(monkeypatch, _FakeFRED())
    out_path = tmp_path / "live.pdf"
    rc, out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END,
         "--format", "pdf", "--output", str(out_path)], capsys)
    assert rc == 0, err
    assert out == ""
    assert out_path.read_bytes().startswith(b"%PDF")


def test_live_pdf_requires_output(monkeypatch, capsys):
    pytest.importorskip("reportlab")
    _patch_factory(monkeypatch, _FakeFRED())
    rc, _out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END,
         "--format", "pdf"], capsys)
    assert rc == 2
    assert "--output" in err


# ─── failure path ──────────────────────────────────────────────────


def test_live_failure_exits_nonzero_clean(monkeypatch, capsys):
    _patch_factory(monkeypatch, _FakeFRED(raise_exc=RuntimeError("FRED 403")))
    rc, out, err = _run(
        ["crisis-dossier-live", "--start", START, "--end", END], capsys)
    assert rc == 1
    assert out == ""
    assert "live dossier unavailable" in err
    assert "Traceback" not in err
