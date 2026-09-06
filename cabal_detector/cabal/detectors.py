"""The individual signals.

Each detector answers one question, returns a normalized 0..1 value and, more
importantly, a sentence a human can check on an explorer. A wallet is only
interesting when several fire at once -- any single one of these has an innocent
explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import DetectorConfig
from .features import WalletActivity
from .models import Signal
from .timeline import TokenTimeline


@dataclass
class TokenContext:
    timeline: TokenTimeline
    activity: dict[str, WalletActivity]
    config: DetectorConfig
    supply: int = 0
    clusters: dict[str, int] = field(default_factory=dict)
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    hub_funders: set[str] = field(default_factory=set)
    deployer_funders: set[str] = field(default_factory=set)

    def share(self, amount: int) -> float:
        return amount / self.supply if self.supply > 0 else 0.0

    def expected_peers(self, window_seconds: int) -> float:
        """How many first-buys a ``+/- window`` span holds at the ambient rate."""
        stamps = sorted(
            a.first_buy_ts
            for a in self.activity.values()
            if a.first_buy_ts is not None and a.buy_rank is not None and a.buy_rank < 50
        )
        if len(stamps) < 3:
            return 0.0
        span = stamps[-1] - stamps[0]
        if span <= 0:
            # Every early buy landed in one instant: co-timing says nothing.
            return float(len(stamps))
        rate = (len(stamps) - 1) / span
        return rate * window_seconds * 2


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def pre_liquidity_allocation(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Tokens held before a pool existed: allocated, not bought."""
    amount = act.free_allocation
    if amount <= 0:
        return None
    share = ctx.share(amount)
    if share < ctx.config.supply_share_floor:
        return None
    # 5% of supply handed out pre-sale saturates the signal.
    value = min(1.0, share / 0.05)
    how = "minted directly to it" if act.minted_to >= act.received_pre_liquidity else "transferred in"
    return Signal(
        name="pre_liquidity_allocation",
        value=value,
        weight=ctx.config.weight("pre_liquidity_allocation"),
        detail=(
            f"held {_pct(share)} of supply before liquidity existed ({how}) — "
            f"an allocation, not a purchase"
        ),
    )


def pre_public_trade(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Acquired after liquidity was added but before the first public trade."""
    amount = max(0, act.received_pre_first_trade - act.free_allocation)
    if amount <= 0:
        return None
    share = ctx.share(amount)
    if share < ctx.config.supply_share_floor:
        return None
    return Signal(
        name="pre_public_trade",
        value=min(1.0, share / 0.03),
        weight=ctx.config.weight("pre_public_trade"),
        detail=(
            f"acquired {_pct(share)} of supply after liquidity was added but "
            f"before the first public trade"
        ),
    )


def snipe_latency(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Bought in the opening block or two -- needs prior knowledge or a bot."""
    if act.blocks_after_open is None or act.blocks_after_open < 0:
        return None
    window = ctx.config.snipe_blocks
    if act.blocks_after_open > window:
        return None
    value = 1.0 - (act.blocks_after_open / (window + 1))
    where = "the same block as" if act.blocks_after_open == 0 else f"{act.blocks_after_open} block(s) after"
    return Signal(
        name="snipe_latency",
        value=value,
        weight=ctx.config.weight("snipe_latency"),
        detail=f"bought in {where} the first public trade",
    )


def early_buyer_rank(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    if act.buy_rank is None:
        return None
    horizon = 50
    if act.buy_rank >= horizon:
        return None
    if (
        act.blocks_after_open is not None
        and act.blocks_after_open > ctx.config.early_buyer_window
        and act.buy_rank > 20
    ):
        return None
    value = (horizon - act.buy_rank) / horizon
    return Signal(
        name="early_buyer_rank",
        value=value,
        weight=ctx.config.weight("early_buyer_rank"),
        detail=f"buyer #{act.buy_rank + 1} of {len(ctx.timeline.buy_order)}",
    )


def fresh_wallet(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """First funded shortly before the launch: a wallet made for this trade."""
    launch_ts = ctx.timeline.liquidity_ts or ctx.timeline.deploy_ts
    if not launch_ts or act.first_funding_ts is None:
        return None
    age = launch_ts - act.first_funding_ts
    if age < 0 or age > ctx.config.fresh_wallet_seconds:
        return None
    value = 1.0 - (age / ctx.config.fresh_wallet_seconds)
    hours = age / 3600
    return Signal(
        name="fresh_wallet",
        value=value,
        weight=ctx.config.weight("fresh_wallet"),
        detail=f"wallet first funded {hours:.1f}h before launch",
    )


def deployer_link(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Money ties the wallet to whoever deployed the token."""
    deployer = ctx.timeline.deployer
    if not deployer:
        return None
    if act.wallet == deployer:
        return Signal(
            name="deployer_link",
            value=1.0,
            weight=ctx.config.weight("deployer_link"),
            detail="this wallet is the token deployer / initial supply holder",
        )
    if act.received_from_deployer > 0:
        share = ctx.share(act.received_from_deployer)
        return Signal(
            name="deployer_link",
            value=1.0,
            weight=ctx.config.weight("deployer_link"),
            detail=f"received {_pct(share)} of supply directly from the deployer",
        )
    if deployer in act.funders:
        return Signal(
            name="deployer_link",
            value=0.9,
            weight=ctx.config.weight("deployer_link"),
            detail="gas funded by the token deployer",
        )
    shared = act.funders & ctx.deployer_funders
    if shared:
        return Signal(
            name="deployer_link",
            value=0.7,
            weight=ctx.config.weight("deployer_link"),
            detail=(
                f"shares a funding source with the deployer ({sorted(shared)[0]})"
            ),
        )
    return None


def funding_cluster(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    cluster_id = ctx.clusters.get(act.wallet)
    if cluster_id is None:
        return None
    size = ctx.cluster_sizes.get(cluster_id, 0)
    if size < 2:
        return None
    return Signal(
        name="funding_cluster",
        value=min(1.0, (size - 1) / 4),
        weight=ctx.config.weight("funding_cluster"),
        detail=f"part of a {size}-wallet cluster linked by shared funding",
    )


def synchronized_buys(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Entered alongside more wallets than the launch's own pace explains.

    Raw co-timing is worthless on a fast chain: during a hot launch everyone
    buys within seconds of everyone else. What matters is the *excess* over the
    prevailing buy rate, so the baseline is measured from the launch itself.
    """
    if act.first_buy_ts is None:
        return None
    window = ctx.config.sync_window_seconds
    peers = [
        other.wallet
        for other in ctx.activity.values()
        if other.wallet != act.wallet
        and other.first_buy_ts is not None
        and abs(other.first_buy_ts - act.first_buy_ts) <= window
        and other.buy_rank is not None
        and other.buy_rank < 50
    ]
    if len(peers) < ctx.config.min_sync_peers:
        return None

    expected = ctx.expected_peers(window)
    # Demand a clear multiple of the ambient rate before calling it coordination.
    if len(peers) < max(ctx.config.min_sync_peers, expected * 2):
        return None
    value = min(1.0, (len(peers) - expected) / 5)
    if value <= 0:
        return None
    return Signal(
        name="synchronized_buys",
        value=value,
        weight=ctx.config.weight("synchronized_buys"),
        detail=(
            f"entered within {window}s of {len(peers)} other early wallets "
            f"(~{expected:.1f} expected at this launch's buy rate)"
        ),
    )


def bought_before_pump(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Already holding when the run-up started, having bought before it."""
    if not ctx.timeline.pumps:
        return None
    pump = ctx.timeline.pumps[0]
    if act.holdings_at_pump_start <= 0:
        return None
    if act.first_buy_ts is not None and act.first_buy_ts > pump.start_ts:
        return None
    share = ctx.share(act.holdings_at_pump_start)
    if share < ctx.config.supply_share_floor:
        return None
    return Signal(
        name="bought_before_pump",
        value=min(1.0, share / 0.02),
        weight=ctx.config.weight("bought_before_pump"),
        detail=(
            f"held {_pct(share)} of supply when a {pump.multiple:.1f}x run-up "
            f"began, all of it acquired beforehand"
        ),
    )


def sell_into_pump(act: WalletActivity, ctx: TokenContext) -> Signal | None:
    """Distributed into the run-up it was early to."""
    if not ctx.timeline.pumps or act.sold_during_pump <= 0:
        return None
    pump = ctx.timeline.pumps[0]
    basis = max(act.peak_holdings, act.holdings_at_pump_start, 1)
    share_sold = act.sold_during_pump / basis
    if share_sold < ctx.config.sell_into_pump_share:
        return None
    roi = act.roi
    roi_text = f", {roi:.1f}x on quote spent" if roi and roi > 1 else ""
    return Signal(
        name="sell_into_pump",
        value=min(1.0, share_sold),
        weight=ctx.config.weight("sell_into_pump"),
        detail=(
            f"sold {share_sold * 100:.0f}% of its position into the "
            f"{pump.multiple:.1f}x run-up{roi_text}"
        ),
    )


TOKEN_DETECTORS = (
    pre_liquidity_allocation,
    pre_public_trade,
    snipe_latency,
    early_buyer_rank,
    fresh_wallet,
    deployer_link,
    funding_cluster,
    synchronized_buys,
    bought_before_pump,
    sell_into_pump,
)


def cross_token_recidivism(
    tokens_flagged: list[str], config: DetectorConfig
) -> Signal | None:
    """The strongest signal available: being early, repeatedly, across tokens.

    One lucky early buy is luck. The same wallet in the opening cohort of
    several unrelated launches is a business.
    """
    count = len(tokens_flagged)
    if count < config.min_recidivism_tokens:
        return None
    return Signal(
        name="cross_token_recidivism",
        value=min(1.0, (count - 1) / 3),
        weight=config.weight("cross_token_recidivism"),
        detail=(
            f"in the early/allocated cohort for {count} separate tokens: "
            + ", ".join(tokens_flagged[:5])
            + ("..." if count > 5 else "")
        ),
    )
