"""Live collection: RPC in, ``TokenSnapshot`` out.

Ordering matters here. Transfers come first, then a provisional timeline, then
the funding scan -- because the funding scan is by far the most expensive call
path and is only worth running for the wallets the timeline says were early.
"""

from __future__ import annotations

from typing import Sequence

from .models import TokenSnapshot, normalize
from .sources.rpc import RpcSource
from .timeline import build_timeline, infer_pools


def collect_token(
    source: RpcSource,
    token: str,
    *,
    from_block: int | None = None,
    to_block: int | None = None,
    quote_tokens: Sequence[str] = (),
    pools: Sequence[str] = (),
    v2_factories: Sequence[str] = (),
    v3_factories: Sequence[str] = (),
    funding_lookback: int = 5_000,
    funding_cohort_size: int = 150,
    with_funding: bool = True,
    progress=lambda msg: None,
) -> TokenSnapshot:
    token = normalize(token)
    chain = source.chain
    latest = source.block_number()
    to_block = latest if to_block is None else to_block

    if from_block is None:
        progress("locating deploy block...")
        from_block = source.find_deploy_block(token, 0, to_block)
        progress(f"deploy block ~{from_block}")

    symbol, decimals = source.token_metadata(token)
    progress(f"scanning {symbol or token} transfers {from_block}..{to_block}")
    transfers = source.transfers(token, from_block, to_block)
    progress(f"{len(transfers)} transfers")

    pool_set = {normalize(p) for p in pools}
    factories_v2 = tuple(v2_factories) or chain.v2_factories
    factories_v3 = tuple(v3_factories) or chain.v3_factories
    if factories_v2 or factories_v3:
        discovered = source.find_pools_from_factories(
            token, from_block, to_block, factories_v2, factories_v3
        )
        progress(f"{len(discovered)} pool(s) from factories")
        pool_set |= set(discovered)
    pool_set |= infer_pools(transfers, token)
    progress(f"{len(pool_set)} pool(s) total")

    quotes = [normalize(q) for q in (quote_tokens or chain.quote_tokens)]
    if quotes and pool_set:
        progress("fetching quote-side legs for pricing...")
        transfers = transfers + source.quote_legs(
            quotes, sorted(pool_set), from_block, to_block
        )

    mints = [t for t in transfers if t.token == token and t.is_mint]
    deployer = max(mints, key=lambda t: t.amount).recipient if mints else ""

    snapshot = TokenSnapshot(
        token=token,
        chain=chain.name,
        chain_id=chain.chain_id,
        symbol=symbol,
        decimals=decimals,
        from_block=from_block,
        to_block=to_block,
        transfers=transfers,
        pools=sorted(pool_set),
        deployer=deployer,
    )

    if with_funding:
        timeline = build_timeline(snapshot, quote_tokens=set(quotes))
        cohort = _funding_cohort(timeline, deployer, funding_cohort_size)
        if cohort:
            launch_block = timeline.liquidity_block or timeline.deploy_block or from_block
            start = max(0, launch_block - funding_lookback)
            progress(
                f"scanning native funding for {len(cohort)} wallets "
                f"over blocks {start}..{launch_block}"
            )
            snapshot.funding = source.funding_edges(cohort, start, launch_block)
            progress(f"{len(snapshot.funding)} funding edge(s)")
    return snapshot


def _funding_cohort(timeline, deployer: str, limit: int) -> list[str]:
    cohort: list[str] = []
    seen: set[str] = set()
    if deployer:
        cohort.append(deployer)
        seen.add(deployer)
    for wallet in timeline.buy_order[:limit]:
        if wallet not in seen and wallet not in timeline.pools:
            cohort.append(wallet)
            seen.add(wallet)
    return cohort[:limit]
