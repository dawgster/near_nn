"""Find the launches worth looking at.

The workflow this supports: enumerate every pool created in a block range, work
out which asset is the quote side, cheaply price each new token, and keep only
the ones that actually ran. Wallet scoring -- the expensive part, with its
funding scans -- then runs on that shortlist instead of on every token that ever
had a pool.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from .models import DEAD_ADDRESSES, TokenSnapshot, normalize
from .screen import PumpVerdict, ScreenCriteria, screen_timeline
from .timeline import build_timeline


@dataclass
class Candidate:
    token: str
    pools: list[str] = field(default_factory=list)
    quote: str = ""
    verdict: PumpVerdict | None = None


def infer_quote_tokens(
    pairs: Sequence[tuple[str, str, str]], min_pools: int = 3
) -> list[str]:
    """Guess the quote assets from pool composition.

    The wrapped native token and the main stables appear on one side of most
    pools; a launch token appears in one or two. Counting sides finds them
    without needing the chain's addresses hard-coded anywhere.
    """
    counts: Counter[str] = Counter()
    for _, token0, token1 in pairs:
        counts[normalize(token0)] += 1
        counts[normalize(token1)] += 1
    return [
        token
        for token, count in counts.most_common()
        if count >= min_pools and token not in DEAD_ADDRESSES
    ]


def build_candidates(
    pairs: Sequence[tuple[str, str, str]], quote_tokens: Sequence[str]
) -> list[Candidate]:
    """Turn ``(pool, token0, token1)`` rows into one candidate per launch token."""
    quotes = {normalize(q) for q in quote_tokens}
    by_token: dict[str, Candidate] = {}
    for pool, token0, token1 in pairs:
        pool, token0, token1 = normalize(pool), normalize(token0), normalize(token1)
        if token0 in quotes and token1 in quotes:
            continue  # a quote/quote pool, not a launch
        if token0 in quotes:
            token, quote = token1, token0
        elif token1 in quotes:
            token, quote = token0, token1
        else:
            continue  # neither side is a known quote: cannot price it
        candidate = by_token.setdefault(token, Candidate(token=token, quote=quote))
        if pool not in candidate.pools:
            candidate.pools.append(pool)
    return list(by_token.values())


def screen_candidate(
    source,
    candidate: Candidate,
    from_block: int,
    to_block: int,
    criteria: ScreenCriteria | None = None,
    *,
    progress=lambda msg: None,
) -> Candidate:
    """Price one candidate with the minimum RPC work.

    Transfers plus the quote legs only -- no funding scan, no deploy-block
    search. If the token fails here it never costs anything more.
    """
    symbol, decimals = source.token_metadata(candidate.token)
    transfers = source.transfers(candidate.token, from_block, to_block)
    if candidate.pools:
        transfers = transfers + source.quote_legs(
            [candidate.quote], candidate.pools, from_block, to_block
        )
    snapshot = TokenSnapshot(
        token=candidate.token,
        symbol=symbol,
        decimals=decimals,
        from_block=from_block,
        to_block=to_block,
        transfers=transfers,
        pools=list(candidate.pools),
    )
    timeline = build_timeline(snapshot, quote_tokens={candidate.quote})
    candidate.verdict = screen_timeline(timeline, criteria)
    progress(
        f"{symbol or candidate.token[:10]}: "
        f"{'PASS' if candidate.verdict.passed else 'skip'} "
        f"{candidate.verdict.multiple:.2f}x, {candidate.verdict.unique_buyers} buyers"
    )
    return candidate


def discover_pumped_tokens(
    source,
    from_block: int,
    to_block: int,
    *,
    v2_factories: Sequence[str] = (),
    v3_factories: Sequence[str] = (),
    quote_tokens: Sequence[str] = (),
    criteria: ScreenCriteria | None = None,
    max_tokens: int = 100,
    progress=lambda msg: None,
) -> list[Candidate]:
    """Enumerate launches in a block range and return them screened, best first."""
    pairs = source.discover_pools(from_block, to_block, v2_factories, v3_factories)
    progress(f"{len(pairs)} pool(s) created in range")
    if not pairs:
        return []

    quotes = [normalize(q) for q in quote_tokens] or infer_quote_tokens(pairs)
    progress(f"quote asset(s): {', '.join(q[:10] for q in quotes) or 'none inferred'}")

    candidates = build_candidates(pairs, quotes)
    progress(f"{len(candidates)} launch token(s) to screen")

    screened = []
    for candidate in candidates[:max_tokens]:
        try:
            screened.append(
                screen_candidate(source, candidate, from_block, to_block, criteria, progress=progress)
            )
        except Exception as exc:  # one bad token must not sink the sweep
            progress(f"{candidate.token[:10]}: error, skipped ({exc})")
    screened.sort(
        key=lambda c: (c.verdict.passed, c.verdict.multiple) if c.verdict else (False, 0),
        reverse=True,
    )
    return screened
