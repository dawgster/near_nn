"""Per-wallet feature extraction against a token's timeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import DEAD_ADDRESSES, FundingEdge, TokenSnapshot, normalize
from .timeline import TokenTimeline


@dataclass
class WalletActivity:
    wallet: str
    token: str = ""

    # Acquisition
    first_seen_block: int = 0
    first_seen_ts: int = 0
    received_pre_liquidity: int = 0
    received_pre_first_trade: int = 0
    received_from_deployer: int = 0
    minted_to: int = 0
    buy_rank: int | None = None
    first_buy_block: int | None = None
    first_buy_ts: int | None = None
    blocks_after_open: int | None = None

    # Trading
    tokens_bought: int = 0
    tokens_sold: int = 0
    quote_spent: int = 0
    quote_received: int = 0
    buy_count: int = 0
    sell_count: int = 0

    # Position around the first pump
    holdings_at_pump_start: int = 0
    sold_during_pump: int = 0
    bought_during_pump: int = 0
    peak_holdings: int = 0

    # Funding graph
    funders: set[str] = field(default_factory=set)
    funded: set[str] = field(default_factory=set)
    first_funding_ts: int | None = None
    first_funding_block: int | None = None

    @property
    def net_position(self) -> int:
        return (
            self.minted_to
            + self.received_pre_liquidity
            + self.tokens_bought
            - self.tokens_sold
        )

    @property
    def realized_quote_pnl(self) -> int:
        return self.quote_received - self.quote_spent

    @property
    def roi(self) -> float | None:
        if self.quote_spent <= 0:
            return None
        return self.quote_received / self.quote_spent

    @property
    def free_allocation(self) -> int:
        """Tokens obtained without paying a pool: airdrop, team allocation, OTC."""
        return self.minted_to + self.received_pre_liquidity

    def to_json(self) -> dict:
        return {
            "first_seen_block": self.first_seen_block,
            "buy_rank": self.buy_rank,
            "blocks_after_open": self.blocks_after_open,
            "free_allocation": str(self.free_allocation),
            "received_pre_first_trade": str(self.received_pre_first_trade),
            "tokens_bought": str(self.tokens_bought),
            "tokens_sold": str(self.tokens_sold),
            "quote_spent": str(self.quote_spent),
            "quote_received": str(self.quote_received),
            "roi": round(self.roi, 3) if self.roi is not None else None,
            "sold_during_pump": str(self.sold_during_pump),
            "holdings_at_pump_start": str(self.holdings_at_pump_start),
            "funders": sorted(self.funders),
        }


def build_activity(
    snapshot: TokenSnapshot, timeline: TokenTimeline
) -> dict[str, WalletActivity]:
    token = normalize(snapshot.token)
    pools = timeline.pools
    deployer = timeline.deployer
    activity: dict[str, WalletActivity] = {}

    def get(addr: str) -> WalletActivity:
        if addr not in activity:
            activity[addr] = WalletActivity(wallet=addr, token=token)
        return activity[addr]

    liquidity_block = timeline.liquidity_block
    open_block = timeline.first_trade_block
    pump = timeline.pumps[0] if timeline.pumps else None

    transfers = sorted(
        (t for t in snapshot.transfers if t.token == token),
        key=lambda t: (t.block, t.log_index),
    )

    balances: dict[str, int] = defaultdict(int)
    for t in transfers:
        if not t.is_mint:
            balances[t.sender] -= t.amount
        if not t.is_burn:
            balances[t.recipient] += t.amount

        for addr in (t.sender, t.recipient):
            if addr in DEAD_ADDRESSES or addr in pools:
                continue
            act = get(addr)
            if act.first_seen_block == 0:
                act.first_seen_block = t.block
                act.first_seen_ts = t.timestamp
            act.peak_holdings = max(act.peak_holdings, balances[addr])

        if t.recipient in DEAD_ADDRESSES or t.recipient in pools:
            continue
        act = get(t.recipient)
        if t.is_mint:
            act.minted_to += t.amount
        elif t.sender not in pools:
            # A plain wallet-to-wallet move. Before liquidity exists it is an
            # allocation; before the first public trade it is still a head start.
            if liquidity_block is not None and t.block < liquidity_block:
                act.received_pre_liquidity += t.amount
            elif liquidity_block is None:
                act.received_pre_liquidity += t.amount
            if open_block is not None and t.block < open_block:
                act.received_pre_first_trade += t.amount
            if deployer and t.sender == deployer:
                act.received_from_deployer += t.amount

        # Snapshot every wallet's balance as the pump kicks off.
        if pump is not None and t.timestamp <= pump.start_ts:
            for addr in (t.sender, t.recipient):
                if addr in DEAD_ADDRESSES or addr in pools:
                    continue
                get(addr).holdings_at_pump_start = balances[addr]

    for trade in timeline.trades:
        act = get(trade.wallet)
        if trade.is_buy:
            act.tokens_bought += trade.token_delta
            act.quote_spent += trade.quote_amount
            act.buy_count += 1
            if act.first_buy_block is None:
                act.first_buy_block = trade.block
                act.first_buy_ts = trade.timestamp
                act.buy_rank = timeline.buy_rank(trade.wallet)
                if open_block is not None:
                    act.blocks_after_open = trade.block - open_block
            if open_block is not None and trade.block < open_block:
                act.received_pre_first_trade += trade.token_delta
        else:
            act.tokens_sold += -trade.token_delta
            act.quote_received += trade.quote_amount
            act.sell_count += 1
        if pump is not None and pump.contains(trade.timestamp):
            if trade.is_buy:
                act.bought_during_pump += trade.token_delta
            else:
                act.sold_during_pump += -trade.token_delta

    apply_funding(activity, snapshot.funding)
    return activity


def apply_funding(
    activity: dict[str, WalletActivity], funding: list[FundingEdge]
) -> None:
    """Attach native-token funding edges to the wallets they touch."""
    for edge in sorted(funding, key=lambda e: (e.block, e.tx_hash)):
        if edge.recipient in activity:
            act = activity[edge.recipient]
            act.funders.add(edge.sender)
            if act.first_funding_ts is None:
                act.first_funding_ts = edge.timestamp
                act.first_funding_block = edge.block
        if edge.sender in activity:
            activity[edge.sender].funded.add(edge.recipient)
