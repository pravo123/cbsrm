"""Tests for the ``cbsrm crisis-dossier`` CLI export command.

The command is a thin composition layer over
``cbsrm.diagnostics.build_crisis_dossier`` and the ``cbsrm.reporting``
renderer.  These tests pin the externally observable CLI contract:

  * exit codes
  * JSON / Markdown output shape
  * UTF-8 safety (the report renderer emits "→" and em-dashes which would
    crash a naive ``sys.stdout.write`` on Windows cp1252 consoles)
  * deterministic output (same args → byte-identical output)
  * graceful failure on unknown windows
  * no external I/O (offline / fixture-backed)

The tests deliberately do **not** re-validate the dossier or renderer
internals — those are covered by ``tests/test_crisis_dossiers.py`` and
``tests/test_report_renderer.py``.
"""
from __future__ import annotations

import json

import pytest

from cbsrm.cli import main
from cbsrm.diagnostics import list_dossier_windows


# ─── helpers ─────────────────────────────────────────────────────────


def _run(argv, capsys):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# ─── JSON format ─────────────────────────────────────────────────────


def test_default_format_is_json(capsys):
    rc, out, err = _run(["crisis-dossier", "2008Q4"], capsys)
    assert rc == 0, err
    assert err == ""
    payload = json.loads(out)
    assert set(payload.keys()) >= {"report", "dossier"}
    assert payload["report"]["kind"] == "crisis_window_dossier"
    assert payload["dossier"]["window_id"] == "2008Q4"


def test_explicit_json_format(capsys):
    rc, out, _err = _run(
        ["crisis-dossier", "2020Q1", "--format", "json"], capsys,
    )
    assert rc == 0
    payload = json.loads(out)
    assert payload["dossier"]["window_id"] == "2020Q1"
    # round-trip serialization sanity (the payload claims to be JSON-clean)
    json.dumps(payload)


def test_json_emits_unicode_via_ensure_ascii_false(capsys):
    """The renderer/payload uses U+2192 (→) in the composition spec — the
    CLI must emit it as a literal UTF-8 character, not as ``\\u2192``."""
    rc, out, _err = _run(["crisis-dossier", "2008Q4"], capsys)
    assert rc == 0
    # If we ever regressed to ensure_ascii=True the literal arrow would be
    # absent and an escape sequence would appear instead.
    assert "→" in out
    assert "\\u2192" not in out


@pytest.mark.parametrize("window", list_dossier_windows())
def test_all_supported_windows_render_json(window, capsys):
    rc, out, err = _run(["crisis-dossier", window, "--format", "json"], capsys)
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["dossier"]["window_id"] == window


# ─── Markdown format ─────────────────────────────────────────────────


def test_markdown_format_returns_text_report(capsys):
    rc, out, err = _run(
        ["crisis-dossier", "2008Q4", "--format", "markdown"], capsys,
    )
    assert rc == 0, err
    assert err == ""
    # The renderer guarantees a top-level "# " title.
    assert out.startswith("# "), out[:80]
    # Required H2 sections from the renderer contract. (Section names
    # are pinned by tests/test_report_renderer.py — we re-check here only
    # to confirm the CLI pipeline delivers them unchanged.)
    for marker in (
        "## Shock summary",
        "## Phase classification",
        "## Macro event scores",
        "## Replay summary",
        "## Network stress summary",
        "## Research notes",
        "## Spec",
    ):
        assert marker in out, f"missing section: {marker}"
    # NFA / research-only disclaimer must be carried through.
    assert "Disclaimer" in out, "disclaimer missing from markdown export"


def test_markdown_title_prefix_is_applied(capsys):
    prefix = "DRAFT — "
    rc, out, _err = _run(
        [
            "crisis-dossier", "2020Q1",
            "--format", "markdown",
            "--title-prefix", prefix,
        ],
        capsys,
    )
    assert rc == 0
    first_line = out.splitlines()[0]
    assert first_line.startswith(f"# {prefix}"), first_line


def test_markdown_emits_unicode_arrow(capsys):
    """The composition footer contains U+2192; the UTF-8-safe writer must
    deliver it intact even on Windows cp1252 (this would have crashed
    before the ``_write_stdout_utf8_safe`` helper landed)."""
    rc, out, _err = _run(
        ["crisis-dossier", "2023Q1", "--format", "markdown"], capsys,
    )
    assert rc == 0
    assert "→" in out


@pytest.mark.parametrize("window", list_dossier_windows())
def test_all_supported_windows_render_markdown(window, capsys):
    rc, out, err = _run(
        ["crisis-dossier", window, "--format", "markdown"], capsys,
    )
    assert rc == 0, err
    assert window in out


# ─── Error handling ──────────────────────────────────────────────────


def test_unknown_window_exits_two_with_clean_stderr(capsys):
    rc, out, err = _run(["crisis-dossier", "1999Q9"], capsys)
    assert rc == 2
    assert out == ""
    assert "unknown crisis-dossier window" in err
    assert "1999Q9" in err
    # Hint must list the supported set so operators can self-recover.
    for window in list_dossier_windows():
        assert window in err
    # Clean error path — no traceback leak.
    assert "Traceback" not in err


def test_invalid_format_choice_argparse_rejects(capsys):
    """argparse should reject unknown ``--format`` values with SystemExit
    rather than reaching the handler."""
    with pytest.raises(SystemExit) as excinfo:
        main(["crisis-dossier", "2008Q4", "--format", "pdf"])
    assert excinfo.value.code != 0


def test_missing_window_argparse_rejects(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["crisis-dossier"])
    assert excinfo.value.code != 0


# ─── Determinism + isolation ─────────────────────────────────────────


def test_repeated_invocation_is_byte_identical(capsys):
    rc1, out1, _err1 = _run(
        ["crisis-dossier", "2008Q4", "--format", "json"], capsys,
    )
    rc2, out2, _err2 = _run(
        ["crisis-dossier", "2008Q4", "--format", "json"], capsys,
    )
    assert rc1 == 0 and rc2 == 0
    assert out1 == out2, "JSON export must be deterministic"


def test_repeated_markdown_is_byte_identical(capsys):
    rc1, out1, _ = _run(
        ["crisis-dossier", "2020Q1", "--format", "markdown"], capsys,
    )
    rc2, out2, _ = _run(
        ["crisis-dossier", "2020Q1", "--format", "markdown"], capsys,
    )
    assert rc1 == 0 and rc2 == 0
    assert out1 == out2, "Markdown export must be deterministic"


def test_no_external_network_io(monkeypatch, capsys):
    """The dossier path must be 100% offline.  We monkeypatch the two
    HTTP entry points the CBSRM stack uses (``urllib.request.urlopen``
    and ``requests.Session.request``) to raise immediately if touched."""
    import urllib.request

    def _no_urlopen(*_a, **_kw):
        raise AssertionError("crisis-dossier CLI made a urllib network call")

    monkeypatch.setattr(urllib.request, "urlopen", _no_urlopen)

    try:
        import requests  # noqa: F401

        def _no_requests(self, *_a, **_kw):  # pragma: no cover (defensive)
            raise AssertionError(
                "crisis-dossier CLI made a requests network call"
            )

        monkeypatch.setattr("requests.Session.request", _no_requests)
    except ImportError:
        pass

    for window in list_dossier_windows():
        rc, _out, err = _run(
            ["crisis-dossier", window, "--format", "json"], capsys,
        )
        assert rc == 0, err
        rc, _out, err = _run(
            ["crisis-dossier", window, "--format", "markdown"], capsys,
        )
        assert rc == 0, err


# ─── HTML format (v0.9 addition) ────────────────────────────────────


def test_html_format_2008q4_returns_doctype_html(capsys):
    """`--format html` must produce a full HTML document starting with
    the DOCTYPE declaration."""
    pytest.importorskip("markdown")
    rc, out, err = _run(
        ["crisis-dossier", "2008Q4", "--format", "html"], capsys,
    )
    assert rc == 0, err
    assert out.startswith("<!DOCTYPE html>")
    assert "<html" in out
    assert "</html>" in out


@pytest.mark.parametrize("window", list_dossier_windows())
def test_html_format_serves_all_supported_windows(window, capsys):
    pytest.importorskip("markdown")
    rc, out, err = _run(
        ["crisis-dossier", window, "--format", "html"], capsys,
    )
    assert rc == 0, err
    assert "<!DOCTYPE html>" in out
    assert window in out


def test_html_format_contains_disclaimer(capsys):
    pytest.importorskip("markdown")
    rc, out, _err = _run(
        ["crisis-dossier", "2008Q4", "--format", "html"], capsys,
    )
    assert rc == 0
    assert "Disclaimer" in out


def test_html_format_title_prefix_applies(capsys):
    pytest.importorskip("markdown")
    rc, out, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "html",
         "--title-prefix", "WAVERVANIR"],
        capsys,
    )
    assert rc == 0
    assert "WAVERVANIR" in out
    # And it must appear inside the <title> element so the saved-PDF
    # default filename in browsers is meaningful.
    assert "WAVERVANIR" in out.split("</title>")[0]


def test_html_format_is_byte_identical_across_runs(capsys):
    pytest.importorskip("markdown")
    rc1, out1, _ = _run(
        ["crisis-dossier", "2020Q1", "--format", "html"], capsys,
    )
    rc2, out2, _ = _run(
        ["crisis-dossier", "2020Q1", "--format", "html"], capsys,
    )
    assert rc1 == 0 and rc2 == 0
    assert out1 == out2


def test_argparse_accepts_html_in_format_choices(capsys):
    """argparse must reject other formats; html must be accepted as a
    first-class choice alongside json and markdown."""
    # html is accepted (smoke check via successful parse path)
    rc, _out, _err = _run(
        ["crisis-dossier", "2008Q4", "--format", "html"], capsys,
    )
    assert rc == 0
    # Sanity: a bogus format value still fails cleanly (no traceback,
    # non-zero exit). argparse exits via SystemExit on this path.
    with pytest.raises(SystemExit) as excinfo:
        main(["crisis-dossier", "2008Q4", "--format", "yaml"])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert err
    assert "Traceback" not in err


# ─── Manifest flag (v0.9 addition) ──────────────────────────────────


def _read_manifest(path):
    import json as _json
    return _json.loads(path.read_text(encoding="utf-8"))


def test_manifest_flag_writes_sibling_file(tmp_path, capsys):
    """`--manifest PATH` writes a deterministic manifest JSON file."""
    out_path = tmp_path / "m.json"
    rc, out, err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--manifest", str(out_path)],
        capsys,
    )
    assert rc == 0, err
    assert out_path.is_file()
    manifest = _read_manifest(out_path)
    # Required top-level shape from cbsrm.reporting.manifest.
    assert set(manifest.keys()) == {
        "manifest_version", "report_id", "window_id", "format",
        "source", "generated_at_utc", "versions", "hashes",
        "disclaimer_present",
    }


def test_manifest_records_source_cli(tmp_path, capsys):
    out_path = tmp_path / "m.json"
    rc, _out, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "markdown", "--manifest", str(out_path)],
        capsys,
    )
    assert rc == 0
    manifest = _read_manifest(out_path)
    assert manifest["source"] == "cli"


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_manifest_format_matches_cli_format(fmt, tmp_path, capsys):
    if fmt == "html":
        pytest.importorskip("markdown")
    out_path = tmp_path / "m.json"
    rc, _out, _err = _run(
        ["crisis-dossier", "2020Q1",
         "--format", fmt, "--manifest", str(out_path)],
        capsys,
    )
    assert rc == 0
    manifest = _read_manifest(out_path)
    assert manifest["format"] == fmt


def test_manifest_output_sha256_matches_stdout(tmp_path, capsys):
    """The hash in the manifest must equal sha256 of the bytes the
    user saw on stdout."""
    import hashlib

    out_path = tmp_path / "m.json"
    rc, stdout, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "markdown", "--manifest", str(out_path)],
        capsys,
    )
    assert rc == 0
    manifest = _read_manifest(out_path)
    expected = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    assert manifest["hashes"]["output_sha256"] == expected


def test_manifest_window_id_pinned(tmp_path, capsys):
    out_path = tmp_path / "m.json"
    rc, _out, _err = _run(
        ["crisis-dossier", "2023Q1",
         "--format", "json", "--manifest", str(out_path)],
        capsys,
    )
    assert rc == 0
    manifest = _read_manifest(out_path)
    assert manifest["window_id"] == "2023Q1"
    assert manifest["report_id"] == "crisis-dossier"


def test_no_file_written_when_manifest_flag_omitted(tmp_path, capsys):
    """Without `--manifest`, no file in tmp_path. Stdout report is
    still emitted as before."""
    rc, out, _err = _run(
        ["crisis-dossier", "2008Q4", "--format", "json"], capsys,
    )
    assert rc == 0
    assert out  # report still on stdout
    assert list(tmp_path.iterdir()) == []  # no side-effect file


def test_stdout_byte_identical_with_and_without_manifest_flag(
    tmp_path, capsys,
):
    """The manifest flag must be purely additive: stdout report
    bytes are byte-identical with or without `--manifest`."""
    rc1, out_without, _ = _run(
        ["crisis-dossier", "2008Q4", "--format", "json"], capsys,
    )
    out_path = tmp_path / "m.json"
    rc2, out_with, _ = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--manifest", str(out_path)],
        capsys,
    )
    assert rc1 == 0 and rc2 == 0
    assert out_without == out_with


# ─── --audit-db flag (v0.9 addition) ────────────────────────────────


def _audit_rows(db_path):
    """Open the sqlite DB and return all audit rows ordered by id."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            """SELECT id, ts, kind, subject, payload_json, hash, prev_hash
                 FROM cbsrm_audit_log ORDER BY id ASC"""
        ).fetchall()
    finally:
        conn.close()


def test_audit_db_creates_sqlite_and_writes_one_row(tmp_path, capsys):
    db_path = tmp_path / "audit.db"
    assert not db_path.exists()
    rc, _out, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc == 0
    assert db_path.is_file()
    rows = _audit_rows(db_path)
    assert len(rows) == 1


def test_audit_db_stderr_line_shape(tmp_path, capsys):
    db_path = tmp_path / "audit.db"
    rc, _out, err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc == 0
    # The stderr line must start with "audit:" and contain row_id /
    # subject / hash. Hash is 64 hex chars from sha256.
    assert err.startswith("audit:")
    assert "row_id=" in err
    assert "subject=report:crisis-dossier:2008Q4:json" in err
    assert "hash=" in err
    # Locate and check the hash is hex-looking.
    hash_token = err.split("hash=", 1)[1].strip().split()[0]
    assert len(hash_token) == 64
    assert all(c in "0123456789abcdef" for c in hash_token)


def test_audit_db_does_not_change_stdout(tmp_path, capsys):
    """The audit-db flag must be purely additive: stdout report bytes
    are byte-identical with or without `--audit-db`."""
    rc1, out_without, _ = _run(
        ["crisis-dossier", "2008Q4", "--format", "json"], capsys,
    )
    db_path = tmp_path / "audit.db"
    rc2, out_with, _ = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc1 == 0 and rc2 == 0
    assert out_without == out_with


def test_audit_db_without_manifest_still_audits(tmp_path, capsys):
    """`--audit-db` alone (no `--manifest`) still appends the audit row
    and writes no manifest file."""
    db_path = tmp_path / "audit.db"
    rc, _out, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc == 0
    rows = _audit_rows(db_path)
    assert len(rows) == 1
    # Only the audit DB exists in tmp_path; no stray manifest file.
    other = [p for p in tmp_path.iterdir() if p != db_path]
    assert other == []


def test_audit_db_with_manifest_writes_both_and_manifest_file_unchanged(
    tmp_path, capsys,
):
    """When both flags are supplied, the manifest file is identical to
    the no-audit case (no embedded audit metadata)."""
    mpath_audit = tmp_path / "m_with_audit.json"
    db_path = tmp_path / "audit.db"
    rc1, _, _ = _run(
        ["crisis-dossier", "2008Q4", "--format", "json",
         "--manifest", str(mpath_audit), "--audit-db", str(db_path)],
        capsys,
    )
    assert rc1 == 0

    mpath_no_audit = tmp_path / "m_no_audit.json"
    rc2, _, _ = _run(
        ["crisis-dossier", "2008Q4", "--format", "json",
         "--manifest", str(mpath_no_audit)],
        capsys,
    )
    assert rc2 == 0

    # Manifest file content is byte-identical with and without
    # `--audit-db`. No audit metadata leaks into the manifest file.
    assert (
        mpath_audit.read_bytes() == mpath_no_audit.read_bytes()
    )
    # And the audit DB has exactly one row.
    assert len(_audit_rows(db_path)) == 1


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_audit_db_subject_format_suffix(fmt, tmp_path, capsys):
    if fmt == "html":
        pytest.importorskip("markdown")
    db_path = tmp_path / "audit.db"
    rc, _out, _err = _run(
        ["crisis-dossier", "2020Q1",
         "--format", fmt, "--audit-db", str(db_path)],
        capsys,
    )
    assert rc == 0
    rows = _audit_rows(db_path)
    assert len(rows) == 1
    _, _ts, kind, subject, _pj, _h, _ph = rows[0]
    assert kind == "REPORT_EXPORTED"
    assert subject == f"report:crisis-dossier:2020Q1:{fmt}"


def test_audit_payload_source_is_cli(tmp_path, capsys):
    import json as _json

    db_path = tmp_path / "audit.db"
    rc, _out, _err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc == 0
    rows = _audit_rows(db_path)
    payload_json = rows[0][4]
    payload = _json.loads(payload_json)
    assert payload["source"] == "cli"
    assert payload["report_id"] == "crisis-dossier"
    assert payload["window_id"] == "2008Q4"
    assert payload["format"] == "json"


def test_audit_two_runs_append_two_linked_rows(tmp_path, capsys):
    db_path = tmp_path / "audit.db"
    rc1, _, _ = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    rc2, _, _ = _run(
        ["crisis-dossier", "2020Q1",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc1 == 0 and rc2 == 0
    rows = _audit_rows(db_path)
    assert len(rows) == 2
    # Linked chain: row 2's prev_hash equals row 1's hash.
    r1_id, _, _, _, _, r1_hash, r1_prev = rows[0]
    r2_id, _, _, _, _, r2_hash, r2_prev = rows[1]
    assert r2_id == r1_id + 1
    assert r1_prev is None
    assert r2_prev == r1_hash
    assert r2_hash != r1_hash


def test_chain_verify_passes_after_cli_audit_writes(tmp_path, capsys):
    """Re-open the audit DB after the CLI run and verify the chain
    via the existing :meth:`AuditChain.verify` API."""
    import sqlite3

    from cbsrm.audit.chain import AuditChain

    db_path = tmp_path / "audit.db"
    rc1, _, _ = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    rc2, _, _ = _run(
        ["crisis-dossier", "2020Q1",
         "--format", "markdown", "--audit-db", str(db_path)],
        capsys,
    )
    rc3, _, _ = _run(
        ["crisis-dossier", "2023Q1",
         "--format", "json", "--audit-db", str(db_path)],
        capsys,
    )
    assert rc1 == 0 and rc2 == 0 and rc3 == 0

    conn = sqlite3.connect(str(db_path))
    try:
        chain = AuditChain(conn)
        ok, broken = chain.verify()
    finally:
        conn.close()
    assert ok is True
    assert broken == []


def test_audit_db_unwritable_path_fails_cleanly(tmp_path, capsys):
    """A path under a non-existent parent dir should fail with exit
    code 2, a clean stderr message, and no traceback."""
    bad_path = tmp_path / "missing_parent" / "audit.db"
    rc, _out, err = _run(
        ["crisis-dossier", "2008Q4",
         "--format", "json", "--audit-db", str(bad_path)],
        capsys,
    )
    assert rc == 2
    assert err
    assert "cannot open audit db" in err
    assert str(bad_path) in err
    assert "Traceback" not in err
