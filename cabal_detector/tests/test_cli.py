"""CLI wiring: the commands run, honour their flags and emit valid formats."""

import json

from cabal.cli import main
from cabal.ingest import collect_token
from cabal.sources.snapshot import save_snapshot
from cabal.synthetic import generate_launch


def test_demo_runs_and_reports(capsys):
    assert main(["demo", "--launches", "2", "--format", "text"]) == 0
    out = capsys.readouterr()
    assert "likely_cabal" in out.out
    assert "not proof of wrongdoing" in out.out
    assert "planted wallets" in out.err


def test_demo_json_is_valid(capsys):
    assert main(["demo", "--launches", "1", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["wallets"][0]["signals"]


def test_analyze_from_a_snapshot_file(tmp_path, capsys):
    launch = generate_launch()
    path = save_snapshot(launch.snapshot, tmp_path / "snap.json")
    assert main(["analyze", "--snapshot", str(path), "--format", "csv"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("wallet,score,tier")
    assert launch.insiders[0] in out


def test_analyze_writes_to_a_file(tmp_path, capsys):
    launch = generate_launch()
    snap = save_snapshot(launch.snapshot, tmp_path / "snap.json")
    dest = tmp_path / "nested" / "report.md"
    assert main(["analyze", "--snapshot", str(snap), "--format", "markdown", "--out", str(dest)]) == 0
    assert "# Cabal wallet report" in dest.read_text()


def test_analyze_with_no_input_fails_cleanly(capsys):
    assert main(["analyze"]) == 2
    assert "nothing to analyze" in capsys.readouterr().err


def test_min_score_filters_output(tmp_path, capsys):
    launch = generate_launch()
    snap = save_snapshot(launch.snapshot, tmp_path / "snap.json")
    main(["analyze", "--snapshot", str(snap), "--format", "csv", "--min-score", "99"])
    high = capsys.readouterr().out.strip().splitlines()
    main(["analyze", "--snapshot", str(snap), "--format", "csv", "--min-score", "0"])
    low = capsys.readouterr().out.strip().splitlines()
    assert len(high) < len(low)


def test_custom_config_is_applied(tmp_path, capsys):
    launch = generate_launch()
    snap = save_snapshot(launch.snapshot, tmp_path / "snap.json")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"score_normalizer": 10.0}))
    main(["analyze", "--snapshot", str(snap), "--config", str(cfg), "--format", "csv", "--min-score", "0"])
    scores = [float(r.split(",")[1]) for r in capsys.readouterr().out.strip().splitlines()[1:]]
    assert max(scores) < 50, "a large normalizer must damp every score"


def test_unreadable_snapshot_reports_an_error(capsys):
    assert main(["analyze", "--snapshot", "/nonexistent/file.json"]) == 1
    assert "error:" in capsys.readouterr().err


def test_collect_token_orders_its_rpc_work():
    """Ingest should scan transfers first, then fund only the early cohort."""
    launch = generate_launch()
    snap = launch.snapshot
    calls = []

    class StubSource:
        chain = type(
            "C", (), {"name": "test", "chain_id": 1, "v2_factories": (), "v3_factories": (), "quote_tokens": ()}
        )()

        def block_number(self):
            return snap.to_block

        def token_metadata(self, token):
            return "CABAL", 18

        def transfers(self, token, lo, hi, topics_extra=None):
            calls.append("transfers")
            return [t for t in snap.transfers if t.token == token]

        def quote_legs(self, quotes, pools, lo, hi):
            calls.append("quote_legs")
            return [t for t in snap.transfers if t.token in quotes]

        def funding_edges(self, addresses, lo, hi):
            calls.append("funding_edges")
            self.funded = list(addresses)
            return [f for f in snap.funding if f.recipient in set(addresses)]

    source = StubSource()
    out = collect_token(
        source,
        snap.token,
        from_block=snap.from_block,
        to_block=snap.to_block,
        quote_tokens=[launch.quote],
        pools=[launch.pool],
    )
    assert calls.index("transfers") < calls.index("funding_edges")
    assert out.deployer == launch.deployer
    assert launch.pool in out.pools
    assert out.funding, "the early cohort should have produced funding edges"
    assert launch.deployer in source.funded


def test_screen_command_separates_runners_from_duds(tmp_path, capsys):
    from cabal.synthetic import generate_dud

    runner, dud = generate_launch(), generate_dud()
    run_path = save_snapshot(runner.snapshot, tmp_path / "run.json")
    dud_path = save_snapshot(dud.snapshot, tmp_path / "dud.json")
    tokens = tmp_path / "pumped.txt"

    assert main([
        "screen", "--snapshot", str(run_path), "--snapshot", str(dud_path),
        "--write-tokens", str(tokens),
    ]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "skip" in out
    assert "1/2 token(s) worth analyzing" in out
    assert tokens.read_text().strip() == runner.snapshot.token


def test_screen_json_format(tmp_path, capsys):
    path = save_snapshot(generate_launch().snapshot, tmp_path / "run.json")
    assert main(["screen", "--snapshot", str(path), "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["passed"] and rows[0]["multiple"] > 3


def test_analyze_screens_duds_out_by_default(tmp_path, capsys):
    from cabal.synthetic import generate_dud

    dud = generate_dud()
    path = save_snapshot(dud.snapshot, tmp_path / "dud.json")
    assert main(["analyze", "--snapshot", str(path), "--format", "csv", "--min-score", "0"]) == 0
    captured = capsys.readouterr()
    assert "screened out DUD" in captured.err
    assert dud.insiders[0] not in captured.out


def test_include_duds_disables_the_screen(tmp_path, capsys):
    from cabal.synthetic import generate_dud

    dud = generate_dud()
    path = save_snapshot(dud.snapshot, tmp_path / "dud.json")
    main(["analyze", "--snapshot", str(path), "--format", "csv", "--min-score", "0", "--include-duds"])
    assert dud.insiders[0] in capsys.readouterr().out


def test_min_pump_threshold_is_honoured(tmp_path, capsys):
    launch = generate_launch()
    path = save_snapshot(launch.snapshot, tmp_path / "run.json")
    main(["analyze", "--snapshot", str(path), "--format", "csv", "--min-score", "0", "--min-pump", "100"])
    captured = capsys.readouterr()
    assert "screened out" in captured.err
    assert launch.insiders[0] not in captured.out


def test_snapshot_reads_a_tokens_file(tmp_path, capsys):
    """`discover`/`screen` write a token list; `snapshot` should consume it."""
    tokens = tmp_path / "tokens.txt"
    tokens.write_text("# from discover\n0x" + "ab" * 20 + "\n\n")
    # No RPC here: a bad URL proves the file was read and the token reached ingest.
    code = main([
        "snapshot", "--tokens-file", str(tokens), "--rpc-url",
        "http://127.0.0.1:1/none", "--out-dir", str(tmp_path), "--quiet",
    ])
    assert code == 1
    assert "RPC call failed" in capsys.readouterr().err


def test_snapshot_without_tokens_fails_cleanly(capsys):
    assert main(["snapshot", "--rpc-url", "http://127.0.0.1:1/none"]) == 2
    assert "no tokens given" in capsys.readouterr().err
