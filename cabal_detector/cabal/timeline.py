"""Launch timeline, trade reconstruction and pump-window detection.

The three anchors that matter for insider detection:

``deploy``      first mint of the token.
``liquidity``   the moment tokens first reach a pool -- the start of the sale.
``first_trade`` the first pool -> wallet buy, i.e. the first moment the public
                could have bought.

Anything a wallet acquires before ``liquidity`` was handed to it, not bought.
Anything acquired between ``liquidity`` and ``first_trade`` was bought ahead of
everyone else.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import DEAD_ADDRESSES, TokenSnapshot, Trade, Transfer, normalize


@dataclass
class PumpWindow:
    start_ts: int
    peak_ts: int
    start_price: float
    peak_price: float
    end_ts: int = 0
    """Where the price falls back through the retrace threshold.

    Distribution happens on both sides of the top, so ``end_ts`` -- not
    ``peak_ts`` -- is the window insider selling is measured against.
    """

    def __post_init__(self) -> None:
        self.end_ts = max(self.end_ts, self.peak_ts)

    @property
    def multiple(self) -> float:
        return self.peak_price / self.start_price if self.start_price > 0 else 0.0

    def contains(self, timestamp: int) -> bool:
        return self.start_ts <= timestamp <= self.end_ts

    def to_json(self) -> dict:
        return {
            "start_ts": self.start_ts,
            "peak_ts": self.peak_ts,
            "end_ts": self.end_ts,
            "duration_s": self.peak_ts - self.start_ts,
            "multiple": round(self.multiple, 2),
        }


@dataclass
class TokenTimeline:
    token: str
    symbol: str = ""
    decimals: int = 18
    deployer: str = ""
    deploy_block: int = 0
    deploy_ts: int = 0
    liquidity_block: int | None = None
    liquidity_ts: int | None = None
    first_trade_block: int | None = None
    first_trade_ts: int | None = None
    pools: set[str] = field(default_factory=set)
    trades: list[Trade] = field(default_factory=list)
    pumps: list[PumpWindow] = field(default_factory=list)
    minted_supply: int = 0
    buy_order: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def buy_rank(self, wallet: str) -> int | None:
        try:
            return self.buy_order.index(wallet)
        except ValueError:
            return None

    def to_json(self) -> dict:
        return {
            "token": self.token,
            "symbol": self.symbol,
            "deployer": self.deployer,
            "deploy_block": self.deploy_block,
            "deploy_ts": self.deploy_ts,
            "liquidity_block": self.liquidity_block,
            "liquidity_ts": self.liquidity_ts,
            "first_trade_block": self.first_trade_block,
            "first_trade_ts": self.first_trade_ts,
            "pools": sorted(self.pools),
            "trades": len(self.trades),
            "buyers": len(self.buy_order),
            "pumps": [p.to_json() for p in self.pumps],
            "warnings": self.warnings,
        }


def infer_pools(
    transfers: list[Transfer],
    token: str,
    *,
    min_two_way_txs: int = 4,
    min_counterparties: int = 4,
) -> set[str]:
    """Spot AMM pools from flow shape alone.

    A pool both sends and receives the token, against many distinct
    counterparties. This is a fallback for when no factory address is
    configured; it can also catch a CEX hot wallet, which is why ``--pool``
    exists to pin the set explicitly.
    """
    token = normalize(token)
    sent: dict[str, set[str]] = defaultdict(set)
    received: dict[str, set[str]] = defaultdict(set)
    counterparties: dict[str, set[str]] = defaultdict(set)
    for t in transfers:
        if t.token != token:
            continue
        if not t.is_mint:
            sent[t.sender].add(t.tx_hash)
            counterparties[t.sender].add(t.recipient)
        if not t.is_burn:
            received[t.recipient].add(t.tx_hash)
            counterparties[t.recipient].add(t.sender)
    pools = set()
    for addr in set(sent) & set(received):
        if addr in DEAD_ADDRESSES:
            continue
        two_way = min(len(sent[addr]), len(received[addr]))
        if two_way >= min_two_way_txs and len(counterparties[addr]) >= min_counterparties:
            pools.add(addr)
    return pools


def _resolve_router_hops(
    tx_transfers: list[Transfer], token: str, pools: set[str]
) -> dict[str, str]:
    """Map intermediate hop addresses to the wallet that ends up with the tokens.

    A buy routed through an aggregator lands as pool -> router -> wallet. Without
    this the router gets flagged as the earliest buyer of every token on the
    chain.
    """
    forwarded: dict[str, str] = {}
    for t in tx_transfers:
        if t.token != token or t.sender in pools or t.recipient in pools:
            continue
        if t.sender in DEAD_ADDRESSES or t.recipient in DEAD_ADDRESSES:
            continue
        forwarded[t.sender] = t.recipient
    resolved: dict[str, str] = {}
    for start in forwarded:
        seen = {start}
        current = start
        while current in forwarded and forwarded[current] not in seen:
            current = forwarded[current]
            seen.add(current)
        if current != start:
            resolved[start] = current
    return resolved


def build_trades(
    transfers: list[Transfer],
    token: str,
    pools: set[str],
    quote_tokens: set[str] | None = None,
) -> list[Trade]:
    """Reconstruct wallet-level trades from transfers against pool addresses."""
    token = normalize(token)
    quote_tokens = {normalize(q) for q in (quote_tokens or set())}
    by_tx: dict[str, list[Transfer]] = defaultdict(list)
    for t in transfers:
        by_tx[t.tx_hash].append(t)

    trades: list[Trade] = []
    for tx_hash, group in by_tx.items():
        token_legs = [t for t in group if t.token == token]
        pool_legs = [
            t for t in token_legs if (t.sender in pools) != (t.recipient in pools)
        ]
        if not pool_legs:
            continue
        hops = _resolve_router_hops(group, token, pools)

        # Quote-side movement for the same pools, used to price the trade.
        quote_in: dict[str, int] = defaultdict(int)
        quote_out: dict[str, int] = defaultdict(int)
        for t in group:
            if t.token == token:
                continue
            if quote_tokens and t.token not in quote_tokens:
                continue
            if t.recipient in pools:
                quote_in[t.recipient] += t.amount
            elif t.sender in pools:
                quote_out[t.sender] += t.amount

        # Split the tx's quote flow across its token legs by size.
        buy_total = sum(t.amount for t in pool_legs if t.sender in pools)
        sell_total = sum(t.amount for t in pool_legs if t.recipient in pools)

        for leg in pool_legs:
            if leg.sender in pools:  # pool -> wallet: a buy
                pool = leg.sender
                wallet = hops.get(leg.recipient, leg.recipient)
                delta = leg.amount
                share = (leg.amount / buy_total) if buy_total else 0.0
                quote = int(quote_in.get(pool, 0) * share)
            else:  # wallet -> pool: a sell
                pool = leg.recipient
                wallet = leg.sender
                # A sell routed through an aggregator arrives at the pool from the
                # router; credit the address that fed the router in this tx.
                for origin, dest in hops.items():
                    if dest == wallet:
                        wallet = origin
                        break
                delta = -leg.amount
                share = (leg.amount / sell_total) if sell_total else 0.0
                quote = int(quote_out.get(pool, 0) * share)
            if wallet in pools or wallet in DEAD_ADDRESSES:
                continue
            trades.append(
                Trade(
                    wallet=wallet,
                    pool=pool,
                    token_delta=delta,
                    quote_amount=quote,
                    block=leg.block,
                    timestamp=leg.timestamp,
                    tx_hash=tx_hash,
                )
            )
    trades.sort(key=lambda t: (t.block, t.timestamp, t.tx_hash))
    return trades


def detect_pumps(
    trades: list[Trade],
    *,
    min_multiple: float = 3.0,
    max_duration_s: int = 6 * 3600,
    retrace: float = 0.5,
) -> list[PumpWindow]:
    """Find price run-ups of at least ``min_multiple`` from a local trough.

    Prices come from the quote/token ratio of each trade, so a token with no
    matched quote leg yields no pumps -- the tool says so rather than inventing
    a series.
    """
    points = [
        (t.timestamp, t.price)
        for t in trades
        if t.price is not None and t.price > 0 and t.timestamp > 0
    ]
    points.sort()
    if len(points) < 3:
        return []

    pumps: list[PumpWindow] = []
    trough_ts, trough_price = points[0]
    i = 1
    while i < len(points):
        ts, price = points[i]
        if price < trough_price:
            trough_ts, trough_price = ts, price
            i += 1
            continue
        if price >= trough_price * min_multiple and ts - trough_ts <= max_duration_s:
            peak_ts, peak_price = ts, price
            end_ts = ts
            j = i + 1
            while j < len(points):
                nts, nprice = points[j]
                if nprice > peak_price:
                    peak_ts, peak_price = nts, nprice
                elif nprice <= peak_price * retrace:
                    break
                end_ts = nts
                j += 1
            pumps.append(
                PumpWindow(
                    start_ts=trough_ts,
                    peak_ts=peak_ts,
                    start_price=trough_price,
                    peak_price=peak_price,
                    end_ts=end_ts,
                )
            )
            i = j
            if i < len(points):
                trough_ts, trough_price = points[i]
                i += 1
            continue
        i += 1
    return pumps


def build_timeline(
    snapshot: TokenSnapshot,
    *,
    quote_tokens: set[str] | None = None,
    extra_pools: set[str] | None = None,
    pump_multiple: float = 3.0,
) -> TokenTimeline:
    token = normalize(snapshot.token)
    transfers = sorted(snapshot.transfers, key=lambda t: (t.block, t.log_index))
    token_transfers = [t for t in transfers if t.token == token]

    pools = {normalize(p) for p in snapshot.pools}
    pools |= {normalize(p) for p in (extra_pools or set())}
    pools |= infer_pools(transfers, token)

    timeline = TokenTimeline(
        token=token, symbol=snapshot.symbol, decimals=snapshot.decimals, pools=pools
    )
    if not token_transfers:
        timeline.warnings.append("no transfers found for this token in the scanned range")
        return timeline

    mints = [t for t in token_transfers if t.is_mint]
    timeline.minted_supply = sum(t.amount for t in mints)
    first = mints[0] if mints else token_transfers[0]
    timeline.deploy_block = first.block
    timeline.deploy_ts = first.timestamp
    timeline.deployer = snapshot.deployer or (
        max(mints, key=lambda t: t.amount).recipient if mints else ""
    )
    if not mints:
        timeline.warnings.append(
            "no mint observed: scan starts after deployment, pre-liquidity signals "
            "may be incomplete"
        )

    # First token movement into a pool == liquidity added == the sale opens.
    for t in token_transfers:
        if t.recipient in pools:
            timeline.liquidity_block = t.block
            timeline.liquidity_ts = t.timestamp
            break
    if snapshot.liquidity_block is not None:
        timeline.liquidity_block = snapshot.liquidity_block

    timeline.trades = build_trades(transfers, token, pools, quote_tokens)

    seen: set[str] = set()
    for trade in timeline.trades:
        if not trade.is_buy:
            continue
        if timeline.first_trade_block is None:
            timeline.first_trade_block = trade.block
            timeline.first_trade_ts = trade.timestamp
        if trade.wallet not in seen:
            seen.add(trade.wallet)
            timeline.buy_order.append(trade.wallet)

    if not pools:
        timeline.warnings.append(
            "no pool identified: pass --pool or --factory, otherwise trade-based "
            "signals are skipped and only allocation signals apply"
        )
    timeline.pumps = detect_pumps(timeline.trades, min_multiple=pump_multiple)
    if not timeline.pumps and timeline.trades:
        timeline.warnings.append(
            "no pump window detected (no priced trades, or no qualifying run-up)"
        )
    return timeline
