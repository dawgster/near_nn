"""End-to-end scoring against the fixture's known ground truth."""

import json

from cabal.analysis import analyze
from cabal.config import DetectorConfig
from cabal.report import to_csv, to_json, to_markdown, to_text
from cabal.synthetic import generate_launch, generate_series

SUSPECT = ("likely_cabal", "suspect")


def test_single_launch_separates_cabal_from_retail():
    launch = generate_launch()
    result = analyze([launch.snapshot])
    flagged = {w.wallet for w in result.wallets if w.tier in SUSPECT}

    assert launch.cabal <= flagged, "every planted wallet should be flagged"
    assert not (flagged - launch.cabal), "no retail wallet should reach suspect"

    worst_cabal = min(w.score for w in result.wallets if w.wallet in launch.cabal)
    best_retail = max(
        (w.score for w in result.wallets if w.wallet in set(launch.retail)), default=0
    )
    assert worst_cabal > best_retail + 20, "the score gap should be decisive"


def test_every_flag_carries_evidence():
    launch = generate_launch()
    result = analyze([launch.snapshot])
    for wallet in result.wallets:
        if wallet.tier in SUSPECT:
            assert wallet.reasons, "a flag with no stated reason is unusable"
            assert len(wallet.signals) >= 2, "one signal alone should not convict"


def test_recidivism_ranks_the_repeat_wallet_top():
    launches = generate_series(3, repeat_wallets=2)
    result = analyze([l.snapshot for l in launches])
    repeaters = {w for w in launches[0].snipers[:2]}

    top = result.wallets[0]
    assert top.wallet in repeaters
    assert any(s.name == "cross_token_recidivism" for s in top.signals)
    assert len(top.tokens) == 3

    # Wallets seen at a single launch must not get the recidivism signal.
    for wallet in result.wallets:
        if len(wallet.tokens) < 2:
            assert not any(s.name == "cross_token_recidivism" for s in wallet.signals)


def test_no_false_positives_across_a_series():
    launches = generate_series(3)
    truth = set().union(*[l.cabal for l in launches])
    result = analyze([l.snapshot for l in launches])
    flagged = {w.wallet for w in result.wallets if w.tier in SUSPECT}
    assert not (flagged - truth)
    assert truth <= flagged


def test_pools_are_never_scored():
    launch = generate_launch()
    result = analyze([launch.snapshot])
    assert launch.pool not in {w.wallet for w in result.wallets}


def test_ignore_list_removes_a_wallet():
    launch = generate_launch()
    target = launch.insiders[0]
    result = analyze([launch.snapshot], ignore={target})
    assert target not in {w.wallet for w in result.wallets}


def test_clusters_group_the_ring():
    launch = generate_launch()
    result = analyze([launch.snapshot])
    assert result.clusters
    biggest = result.clusters[0]
    assert set(launch.insiders) <= set(biggest.members)
    assert biggest.reasons


def test_stricter_config_raises_the_bar():
    launch = generate_launch()
    strict = DetectorConfig(score_normalizer=4.0)
    loose = analyze([launch.snapshot])
    tight = analyze([launch.snapshot], strict)
    assert max(w.score for w in tight.wallets) < max(w.score for w in loose.wallets)


def test_report_formats_render():
    launch = generate_launch()
    result = analyze([launch.snapshot])

    parsed = json.loads(to_json(result))
    assert parsed["wallets"] and parsed["timelines"]
    assert parsed["wallets"][0]["signals"][0]["detail"]

    csv_out = to_csv(result, min_score=0)
    assert csv_out.startswith("wallet,score,tier")
    assert len(csv_out.strip().splitlines()) == len(result.wallets) + 1

    md = to_markdown(result)
    assert "# Cabal wallet report" in md and "Flagged wallets" in md
    assert "not proof of wrongdoing" in md

    assert "not proof of wrongdoing" in to_text(result)


def test_snapshot_roundtrip_preserves_the_verdict(tmp_path):
    from cabal.sources.snapshot import load_snapshot, save_snapshot

    launch = generate_launch()
    path = save_snapshot(launch.snapshot, tmp_path / "snap.json")
    reloaded = load_snapshot(path)
    before = analyze([launch.snapshot])
    after = analyze([reloaded])
    assert [(w.wallet, round(w.score, 6)) for w in before.wallets] == [
        (w.wallet, round(w.score, 6)) for w in after.wallets
    ]


def test_cluster_ids_are_unique_across_tokens():
    """Two rings from two launches must not both render as the same cluster."""
    launches = generate_series(3)
    result = analyze([l.snapshot for l in launches])
    ids = [c.cluster_id for c in result.clusters]
    assert len(ids) == len(set(ids))
    assert len(result.clusters) >= 3, "each launch's ring should form its own cluster"

    by_id = {c.cluster_id: set(c.members) for c in result.clusters}
    for wallet in result.wallets:
        if wallet.cluster_id is not None:
            assert wallet.wallet in by_id[wallet.cluster_id]
