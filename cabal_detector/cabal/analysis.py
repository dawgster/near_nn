"""Orchestration: snapshots in, scored wallets and clusters out."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .clustering import Cluster, build_clusters
from .config import DetectorConfig
from .detectors import TOKEN_DETECTORS, TokenContext, cross_token_recidivism
from .features import WalletActivity, build_activity
from .models import (
    AnalysisResult,
    ClusterReport,
    Signal,
    TokenSnapshot,
    WalletReport,
    normalize,
)
from .timeline import TokenTimeline, build_timeline


@dataclass
class TokenAnalysis:
    snapshot: TokenSnapshot
    timeline: TokenTimeline
    context: TokenContext
    signals: dict[str, list[Signal]] = field(default_factory=dict)
    clusters: list[Cluster] = field(default_factory=list)


def estimate_supply(snapshot: TokenSnapshot, timeline: TokenTimeline) -> int:
    """Observed supply, falling back to summed balances for a partial scan."""
    if timeline.minted_supply > 0:
        return timeline.minted_supply
    balances: dict[str, int] = defaultdict(int)
    token = normalize(snapshot.token)
    for t in snapshot.transfers:
        if t.token != token:
            continue
        if not t.is_mint:
            balances[t.sender] -= t.amount
        if not t.is_burn:
            balances[t.recipient] += t.amount
    return sum(v for v in balances.values() if v > 0)


def _cohort(activity: dict[str, WalletActivity], timeline: TokenTimeline) -> set[str]:
    """Wallets worth clustering: allocated, or in the opening buy cohort."""
    cohort = set()
    for wallet, act in activity.items():
        if act.free_allocation > 0 or act.received_pre_first_trade > 0:
            cohort.add(wallet)
        elif act.buy_rank is not None and act.buy_rank < 50:
            cohort.add(wallet)
    if timeline.deployer:
        cohort.add(timeline.deployer)
    return cohort


def analyze_token(
    snapshot: TokenSnapshot,
    config: DetectorConfig | None = None,
    *,
    quote_tokens: set[str] | None = None,
    extra_pools: set[str] | None = None,
) -> TokenAnalysis:
    config = config or DetectorConfig()
    timeline = build_timeline(
        snapshot,
        quote_tokens=quote_tokens,
        extra_pools=extra_pools,
        pump_multiple=config.pump_multiple,
    )
    activity = build_activity(snapshot, timeline)
    supply = estimate_supply(snapshot, timeline)

    deployer_funders: set[str] = set()
    if timeline.deployer:
        deployer_funders = {
            edge.sender
            for edge in snapshot.funding
            if edge.recipient == timeline.deployer
        }

    cohort = _cohort(activity, timeline)
    assignment, clusters, hubs = build_clusters(activity, config, cohort=cohort)
    cluster_sizes = {c.cluster_id: len(c.members) for c in clusters}

    ctx = TokenContext(
        timeline=timeline,
        activity=activity,
        config=config,
        supply=supply,
        clusters=assignment,
        cluster_sizes=cluster_sizes,
        hub_funders=hubs,
        deployer_funders=deployer_funders,
    )

    signals: dict[str, list[Signal]] = {}
    for wallet, act in activity.items():
        if wallet in timeline.pools:
            continue
        found = [s for s in (d(act, ctx) for d in TOKEN_DETECTORS) if s and s.value > 0]
        if found:
            signals[wallet] = found
    return TokenAnalysis(
        snapshot=snapshot,
        timeline=timeline,
        context=ctx,
        signals=signals,
        clusters=clusters,
    )


def analyze(
    snapshots: list[TokenSnapshot],
    config: DetectorConfig | None = None,
    *,
    quote_tokens: set[str] | None = None,
    extra_pools: set[str] | None = None,
    ignore: set[str] | None = None,
) -> AnalysisResult:
    """Score wallets across one or more token launches.

    Per-signal scores are taken as the best observation across tokens rather than
    summed, so a wallet cannot be pushed over a threshold by one launch alone;
    repetition instead surfaces through the recidivism signal.
    """
    config = config or DetectorConfig()
    ignore = {normalize(a) for a in (ignore or set())}

    analyses = [
        analyze_token(s, config, quote_tokens=quote_tokens, extra_pools=extra_pools)
        for s in snapshots
    ]

    best: dict[str, dict[str, Signal]] = defaultdict(dict)
    wallet_tokens: dict[str, list[str]] = defaultdict(list)
    wallet_stats: dict[str, dict] = defaultdict(dict)
    cluster_reports: list[ClusterReport] = []
    warnings: list[str] = []

    for analysis in analyses:
        token = analysis.timeline.token
        label = analysis.timeline.symbol or token
        warnings.extend(f"[{label}] {w}" for w in analysis.timeline.warnings)
        for wallet, sigs in analysis.signals.items():
            if wallet in ignore or wallet in analysis.timeline.pools:
                continue
            wallet_tokens[wallet].append(label)
            wallet_stats[wallet][label] = analysis.context.activity[wallet].to_json()
            for signal in sigs:
                current = best[wallet].get(signal.name)
                if current is None or signal.contribution > current.contribution:
                    best[wallet][signal.name] = signal

    reports: dict[str, WalletReport] = {}
    for wallet, by_name in best.items():
        report = WalletReport(wallet=wallet, tokens=sorted(set(wallet_tokens[wallet])))
        for signal in by_name.values():
            report.add(signal)
        recidivism = cross_token_recidivism(report.tokens, config)
        report.add(recidivism)
        total = sum(s.contribution for s in report.signals)
        report.score = min(100.0, 100.0 * total / max(config.score_normalizer, 1e-9))
        report.tier = config.tier_for(report.score)
        report.stats = wallet_stats[wallet]
        # Keep the uncapped total so saturated wallets stay comparable.
        report.stats["_weighted_total"] = round(total, 4)
        reports[wallet] = report

    # Cluster ids are assigned per token, so renumber them globally -- otherwise
    # two unrelated rings from two launches both render as "C1".
    next_cluster_id = 1
    for analysis in analyses:
        label = analysis.timeline.symbol or analysis.timeline.token
        for cluster in analysis.clusters:
            members = [m for m in cluster.members if m in reports]
            if len(members) < 2:
                continue
            scores = [reports[m].score for m in members]
            # A tight cluster is worse than its members look alone, but the
            # average keeps one flagged wallet from dragging a whole group up.
            cluster_score = min(100.0, sum(scores) / len(scores) + 5 * (len(members) - 1))
            cluster_id = next_cluster_id
            next_cluster_id += 1
            cluster_reports.append(
                ClusterReport(
                    cluster_id=cluster_id,
                    members=sorted(members, key=lambda m: -reports[m].score),
                    score=cluster_score,
                    reasons=cluster.reasons,
                    tokens=[label],
                )
            )
            for member in members:
                # A wallet in rings across several launches keeps the first;
                # the full membership is in the cluster section either way.
                if reports[member].cluster_id is None:
                    reports[member].cluster_id = cluster_id

    ordered = sorted(reports.values(), key=lambda r: (-r.score, r.wallet))
    return AnalysisResult(
        tokens=[a.timeline.token for a in analyses],
        wallets=ordered,
        clusters=sorted(cluster_reports, key=lambda c: -c.score),
        timelines={a.timeline.token: a.timeline.to_json() for a in analyses},
        warnings=warnings,
    )
