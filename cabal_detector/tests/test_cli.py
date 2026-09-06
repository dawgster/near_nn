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
