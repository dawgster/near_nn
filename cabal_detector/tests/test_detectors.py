"""Each signal should fire on its own scenario and stay quiet otherwise."""

from cabal.analysis import analyze_token
from cabal.clustering import build_clusters
from cabal.config import DetectorConfig
from cabal.features import WalletActivity
from cabal.models import FundingEdge
from cabal.synthetic import generate_launch


def signals_for(analysis, wallet):
    return {s.name: s for s in analysis.signals.get(wallet, [])}


def test_insiders_trip_the_allocation_signals():
    launch = generate_launch()
    analysis = analyze_token(launch.snapshot)
    for insider in launch.insiders:
        names = signals_for(analysis, insider)
        assert "pre_liquidity_allocation" in names
        assert "deployer_link" in names
        assert "sell_into_pump" in names
        assert "an allocation, not a purchase" in names["pre_liquidity_allocation"].detail


def test_snipers_trip_the_timing_signals():
    launch = generate_launch()
    analysis = analyze_token(launch.snapshot)
    hits = [signals_for(analysis, s) for s in launch.snipers]
    assert any("snipe_latency" in h for h in hits)
    assert all("early_buyer_rank" in h for h in hits)
    # Snipers bought at the open, so they must not be credited with an allocation.
    assert all("pre_liquidity_allocation" not in h for h in hits)


def test_retail_does_not_trip_allocation_or_cluster_signals():
    launch = generate_launch()
    analysis = analyze_token(launch.snapshot)
    for wallet in launch.retail:
        names = signals_for(analysis, wallet)
        assert "pre_liquidity_allocation" not in names
        assert "deployer_link" not in names
        assert "funding_cluster" not in names


def test_exchange_hub_funder_does_not_create_a_cluster():
    """A hot wallet funding everyone is not evidence of a shared operator."""
    config = DetectorConfig(hub_funder_threshold=3)
    hub = "0x" + "ee" * 20
    activity = {}
    for i in range(10):
        wallet = f"0x{i:040x}"
        act = WalletActivity(wallet=wallet)
        act.funders.add(hub)
        activity[wallet] = act
    assignment, clusters, hubs = build_clusters(activity, config)
    assert hub in hubs
    assert clusters == [] and assignment == {}


def test_shared_non_hub_funder_creates_a_cluster():
    config = DetectorConfig(hub_funder_threshold=20)
    funder = "0x" + "ff" * 20
    activity = {}
    for i in range(3):
        wallet = f"0x{i:040x}"
        act = WalletActivity(wallet=wallet)
        act.funders.add(funder)
        activity[wallet] = act
    assignment, clusters, hubs = build_clusters(activity, config)
    assert not hubs
    assert len(clusters) == 1 and len(clusters[0].members) == 3
    assert len(set(assignment.values())) == 1


def test_sync_signal_ignores_an_ordinary_busy_launch():
    """Co-timing must be measured against the launch's own buy rate."""
    launch = generate_launch(n_insiders=0, n_snipers=0, n_retail=40)
    analysis = analyze_token(launch.snapshot)
    flagged = [w for w in launch.retail if "synchronized_buys" in signals_for(analysis, w)]
    assert flagged == []


def test_missing_funding_data_degrades_without_crashing():
    launch = generate_launch()
    launch.snapshot.funding = []
    analysis = analyze_token(launch.snapshot)
    for insider in launch.insiders:
        names = signals_for(analysis, insider)
        assert "funding_cluster" not in names
        # Allocation evidence needs no funding graph, so it must survive.
        assert "pre_liquidity_allocation" in names


def test_apply_funding_records_both_directions():
    from cabal.features import apply_funding

    a, b = "0x" + "a" * 40, "0x" + "b" * 40
    activity = {a: WalletActivity(wallet=a), b: WalletActivity(wallet=b)}
    apply_funding(activity, [FundingEdge(a, b, 10, 5, 100, "0x")])
    assert activity[b].funders == {a}
    assert activity[a].funded == {b}
    assert activity[b].first_funding_block == 5
