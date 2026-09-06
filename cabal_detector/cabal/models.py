"""Data model.

Everything downstream is built from two primitives: ERC-20 ``Transfer`` logs and
native-value funding edges. Trades are *derived* from transfers against known
pool addresses rather than from DEX ``Swap`` events, so the analysis works
across Uniswap V2/V3 forks and any other AMM without per-venue decoding.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
DEAD_ADDRESSES = frozenset(
    {
        ZERO_ADDRESS,
        "0x000000000000000000000000000000000000dead",
        "0x0000000000000000000000000000000000000001",
    }
)


def normalize(address: str) -> str:
    """Lowercase 0x-prefixed 20-byte address form used as the key everywhere."""
    addr = address.lower()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    if len(addr) > 42:  # a 32-byte topic word carrying an address
        addr = "0x" + addr[-40:]
    return addr


@dataclass(frozen=True)
class Transfer:
    token: str
    sender: str
    recipient: str
    amount: int
    block: int
    timestamp: int
    tx_hash: str
    log_index: int

    @property
    def is_mint(self) -> bool:
        return self.sender in DEAD_ADDRESSES

    @property
    def is_burn(self) -> bool:
        return self.recipient in DEAD_ADDRESSES

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["amount"] = str(self.amount)  # ints exceed JSON's safe range
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Transfer":
        return cls(
            token=normalize(d["token"]),
            sender=normalize(d["sender"]),
            recipient=normalize(d["recipient"]),
            amount=int(d["amount"]),
            block=int(d["block"]),
            timestamp=int(d["timestamp"]),
            tx_hash=d.get("tx_hash", ""),
            log_index=int(d.get("log_index", 0)),
        )


@dataclass(frozen=True)
class FundingEdge:
    """A native-token (gas) payment from one address to another."""

    sender: str
    recipient: str
    value: int
    block: int
    timestamp: int
    tx_hash: str = ""

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["value"] = str(self.value)
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "FundingEdge":
        return cls(
            sender=normalize(d["sender"]),
            recipient=normalize(d["recipient"]),
            value=int(d.get("value", 0)),
            block=int(d["block"]),
            timestamp=int(d["timestamp"]),
            tx_hash=d.get("tx_hash", ""),
        )


@dataclass(frozen=True)
class Trade:
    """A wallet's leg against a pool, derived from transfers.

    ``token_delta`` is signed from the wallet's point of view: positive is a buy
    (tokens in), negative is a sell. ``quote_amount`` is the paired leg in the
    quote asset when it could be matched in the same transaction, else 0.
    """

    wallet: str
    pool: str
    token_delta: int
    quote_amount: int
    block: int
    timestamp: int
    tx_hash: str

    @property
    def is_buy(self) -> bool:
        return self.token_delta > 0

    @property
    def price(self) -> float | None:
        if self.quote_amount <= 0 or self.token_delta == 0:
            return None
        return self.quote_amount / abs(self.token_delta)


@dataclass
class TokenSnapshot:
    """Everything ingested for one token, serializable for offline re-analysis."""

    token: str
    chain: str = "robinhood"
    chain_id: int = 0
    symbol: str = ""
    decimals: int = 18
    from_block: int = 0
    to_block: int = 0
    transfers: list[Transfer] = field(default_factory=list)
    funding: list[FundingEdge] = field(default_factory=list)
    pools: list[str] = field(default_factory=list)
    deployer: str = ""
    # Block number at which liquidity was first added to a pool, when known
    # from factory/pool events rather than inferred.
    liquidity_block: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "chain": self.chain,
            "chain_id": self.chain_id,
            "symbol": self.symbol,
            "decimals": self.decimals,
            "from_block": self.from_block,
            "to_block": self.to_block,
            "deployer": self.deployer,
            "liquidity_block": self.liquidity_block,
            "pools": sorted(self.pools),
            "transfers": [t.to_json() for t in self.transfers],
            "funding": [f.to_json() for f in self.funding],
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "TokenSnapshot":
        return cls(
            token=normalize(d["token"]),
            chain=d.get("chain", "robinhood"),
            chain_id=int(d.get("chain_id", 0)),
            symbol=d.get("symbol", ""),
            decimals=int(d.get("decimals", 18)),
            from_block=int(d.get("from_block", 0)),
            to_block=int(d.get("to_block", 0)),
            deployer=normalize(d["deployer"]) if d.get("deployer") else "",
            liquidity_block=d.get("liquidity_block"),
            pools=[normalize(p) for p in d.get("pools", [])],
            transfers=[Transfer.from_json(t) for t in d.get("transfers", [])],
            funding=[FundingEdge.from_json(f) for f in d.get("funding", [])],
        )


@dataclass
class Signal:
    """One piece of evidence against a wallet.

    ``value`` is normalized to 0..1 so weights stay comparable; ``detail`` is the
    human-readable reason, which matters more than the number when someone has
    to decide whether a flag is real.
    """

    name: str
    value: float
    weight: float
    detail: str

    @property
    def contribution(self) -> float:
        return max(0.0, min(1.0, self.value)) * self.weight

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "weight": self.weight,
            "contribution": round(self.contribution, 4),
            "detail": self.detail,
        }


@dataclass
class WalletReport:
    wallet: str
    score: float = 0.0
    tier: str = "clear"
    signals: list[Signal] = field(default_factory=list)
    cluster_id: int | None = None
    tokens: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add(self, signal: Signal | None) -> None:
        if signal is not None and signal.value > 0:
            self.signals.append(signal)

    @property
    def reasons(self) -> list[str]:
        return [s.detail for s in sorted(self.signals, key=lambda s: -s.contribution)]

    def to_json(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "score": round(self.score, 2),
            "tier": self.tier,
            "cluster_id": self.cluster_id,
            "tokens": self.tokens,
            "signals": [s.to_json() for s in sorted(self.signals, key=lambda s: -s.contribution)],
            "notes": self.notes,
            "stats": self.stats,
        }


@dataclass
class ClusterReport:
    cluster_id: int
    members: list[str]
    score: float
    reasons: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "size": len(self.members),
            "members": self.members,
            "score": round(self.score, 2),
            "reasons": self.reasons,
            "tokens": self.tokens,
        }


@dataclass
class AnalysisResult:
    tokens: list[str]
    wallets: list[WalletReport]
    clusters: list[ClusterReport]
    timelines: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def flagged(self, min_score: float = 0.0) -> list[WalletReport]:
        return [w for w in self.wallets if w.score > min_score]

    def to_json(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens,
            "timelines": self.timelines,
            "wallets": [w.to_json() for w in self.wallets],
            "clusters": [c.to_json() for c in self.clusters],
            "warnings": self.warnings,
        }


def dedupe_transfers(transfers: Iterable[Transfer]) -> list[Transfer]:
    """Drop duplicate logs (overlapping RPC ranges) and order them canonically."""
    seen: dict[tuple[str, int], Transfer] = {}
    for t in transfers:
        seen[(t.tx_hash, t.log_index)] = t
    return sorted(seen.values(), key=lambda t: (t.block, t.log_index))
