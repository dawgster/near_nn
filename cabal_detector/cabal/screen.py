"""Decide whether a token is even worth analyzing.

A launch that went nowhere has no cabal worth naming: whoever was early made
nothing, and their addresses are noise in a repeat-offender list. So the pump
test runs first and cheaply -- transfers only, no funding scan -- and wallet
scoring only happens for tokens that cleared it.

This also sharpens the strongest signal in the tool. Once the universe is
"coins that actually ran", ``cross_token_recidivism`` stops meaning "this wallet
buys a lot of tokens" and starts meaning "this wallet is early on winners".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .timeline import TokenTimeline


@dataclass
class ScreenCriteria:
    min_pump_multiple: float = 3.0
    """Peak price over the launch baseline. The headline 'did it go anywhere' test."""

    min_unique_buyers: int = 25
    """Guards against a 100x printed by four trades between two wallets."""

    min_trades: int = 20
    min_quote_volume: int = 0
    """Raw quote units. 0 disables; set it to filter out thin books."""

    include_unpriced: bool = False
    """Without a quote token there is no price series and the pump test cannot
    run. Off by default: better to say so than to guess."""

    def to_json(self) -> dict:
        return {
            "min_pump_multiple": self.min_pump_multiple,
            "min_unique_buyers": self.min_unique_buyers,
            "min_trades": self.min_trades,
            "min_quote_volume": self.min_quote_volume,
            "include_unpriced": self.include_unpriced,
        }


@dataclass
class PumpVerdict:
    token: str
    symbol: str = ""
    passed: bool = False
    priced: bool = False
    ath_multiple: float = 0.0
    """Highest price over the launch baseline, whenever it happened."""
    best_window_multiple: float = 0.0
    """Best run-up detected as a contiguous window."""
    unique_buyers: int = 0
    trades: int = 0
    quote_volume: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def multiple(self) -> float:
        return max(self.ath_multiple, self.best_window_multiple)

    def to_json(self) -> dict:
        return {
            "token": self.token,
            "symbol": self.symbol,
            "passed": self.passed,
            "priced": self.priced,
            "multiple": round(self.multiple, 2),
            "ath_multiple": round(self.ath_multiple, 2),
            "best_window_multiple": round(self.best_window_multiple, 2),
            "unique_buyers": self.unique_buyers,
            "trades": self.trades,
            "quote_volume": str(self.quote_volume),
            "reasons": self.reasons,
        }


def _baseline_price(prices: list[float]) -> float:
    """Launch price, taken as the median of the first few trades.

    The very first fill is often an outlier -- a tiny amount, or the deployer
    seeding the book -- so one print should not set the denominator.
    """
    head = sorted(prices[: min(5, len(prices))])
    return head[len(head) // 2] if head else 0.0


def screen_timeline(
    timeline: TokenTimeline, criteria: ScreenCriteria | None = None
) -> PumpVerdict:
    criteria = criteria or ScreenCriteria()
    verdict = PumpVerdict(token=timeline.token, symbol=timeline.symbol)

    verdict.trades = len(timeline.trades)
    verdict.unique_buyers = len(timeline.buy_order)
    verdict.quote_volume = sum(t.quote_amount for t in timeline.trades)

    prices = [t.price for t in timeline.trades if t.price is not None and t.price > 0]
    verdict.priced = len(prices) >= 3
    if verdict.priced:
        baseline = _baseline_price(prices)
        if baseline > 0:
            verdict.ath_multiple = max(prices) / baseline
    verdict.best_window_multiple = max(
        (p.multiple for p in timeline.pumps), default=0.0
    )

    if not verdict.priced:
        if not criteria.include_unpriced:
            verdict.reasons.append(
                "no price series (pass --quote with the pool's quote token, or "
                "--include-unpriced to screen on activity alone)"
            )
        else:
            verdict.reasons.append("unpriced: pump size unknown, judged on activity only")
    elif verdict.multiple < criteria.min_pump_multiple:
        verdict.reasons.append(
            f"peaked at {verdict.multiple:.2f}x, below the {criteria.min_pump_multiple:g}x floor"
        )

    if verdict.unique_buyers < criteria.min_unique_buyers:
        verdict.reasons.append(
            f"only {verdict.unique_buyers} unique buyers (need {criteria.min_unique_buyers})"
        )
    if verdict.trades < criteria.min_trades:
        verdict.reasons.append(
            f"only {verdict.trades} trades (need {criteria.min_trades})"
        )
    if criteria.min_quote_volume and verdict.quote_volume < criteria.min_quote_volume:
        verdict.reasons.append(
            f"quote volume {verdict.quote_volume} below {criteria.min_quote_volume}"
        )

    blocking = [r for r in verdict.reasons if not r.startswith("unpriced:")]
    verdict.passed = not blocking
    if verdict.passed and not verdict.reasons:
        verdict.reasons.append(
            f"{verdict.multiple:.1f}x peak, {verdict.unique_buyers} buyers, "
            f"{verdict.trades} trades"
        )
    return verdict
