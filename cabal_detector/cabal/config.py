"""Tunable thresholds and signal weights.

Weights are deliberately exposed: what counts as a cabal on a fair-launch
memecoin is not what counts on a token with a public presale, and the honest
move is to let the operator retune rather than bake one venue's assumptions in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class DetectorConfig:
    # --- thresholds -------------------------------------------------------
    early_buyer_window: int = 25
    """A buy this many blocks after the first public trade still counts as early."""

    snipe_blocks: int = 2
    """Same-block or near-same-block entry: bot territory."""

    supply_share_floor: float = 0.001
    """Ignore allocations below 0.1% of observed supply as noise."""

    fresh_wallet_seconds: int = 7 * 24 * 3600
    """A wallet first funded less than this before launch reads as purpose-made."""

    sync_window_seconds: int = 30
    """Buys within this window of each other count as synchronized."""

    min_sync_peers: int = 2
    hub_funder_threshold: int = 20
    """A funder paying more cohort wallets than this is treated as an exchange or
    faucet hub, not evidence of a shared operator."""

    pump_multiple: float = 3.0
    sell_into_pump_share: float = 0.3
    min_recidivism_tokens: int = 2

    # --- weights ----------------------------------------------------------
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "pre_liquidity_allocation": 0.35,
            "deployer_link": 0.30,
            "pre_public_trade": 0.25,
            "snipe_latency": 0.20,
            "early_buyer_rank": 0.15,
            "fresh_wallet": 0.10,
            "funding_cluster": 0.20,
            "synchronized_buys": 0.15,
            "sell_into_pump": 0.25,
            "bought_before_pump": 0.20,
            "cross_token_recidivism": 0.35,
        }
    )

    tiers: dict[str, float] = field(
        default_factory=lambda: {
            "likely_cabal": 70.0,
            "suspect": 45.0,
            "watch": 25.0,
        }
    )

    score_normalizer: float = 1.5
    """Total weighted contribution that maps to a score of 100.

    Set below the sum of all weights on purpose: a wallet does not need every
    signal to be damning, but it does need several. Raise it to make the tool
    harder to convince, lower it to widen the net."""

    def weight(self, name: str) -> float:
        return self.weights.get(name, 0.0)

    def tier_for(self, score: float) -> str:
        for name, floor in sorted(self.tiers.items(), key=lambda kv: -kv[1]):
            if score >= floor:
                return name
        return "clear"

    @classmethod
    def load(cls, path: str | Path | None) -> "DetectorConfig":
        cfg = cls()
        if not path:
            return cfg
        data = json.loads(Path(path).read_text())
        weights = {**cfg.weights, **data.pop("weights", {})}
        tiers = {**cfg.tiers, **data.pop("tiers", {})}
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        cfg.weights = weights
        cfg.tiers = tiers
        return cfg

    def to_json(self) -> dict:
        return asdict(self)
