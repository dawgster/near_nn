"""Chain presets.

Robinhood Chain is an EVM (Arbitrum Orbit) L2 that settles to Ethereum, so the
same log-scraping approach works on any EVM chain. The RPC URL and DEX factory
addresses are configuration, never hard requirements -- pass ``--rpc-url`` and
``--factory`` to point the tool at whatever endpoint and venue you actually use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChainConfig:
    name: str
    chain_id: int
    rpc_url: str
    # Native wrapper (WETH-alike) and stables, used to decide which side of a
    # swap is the "quote" leg when pricing a token.
    quote_tokens: tuple[str, ...] = ()
    # DEX factories to watch for pool creation. Empty is fine: pools are also
    # discovered from transfer/swap traffic.
    v2_factories: tuple[str, ...] = ()
    v3_factories: tuple[str, ...] = ()
    # Addresses that are never scored: routers, known bridges, burn addresses.
    infrastructure: frozenset[str] = field(default_factory=frozenset)
    explorer: str = ""
    max_block_range: int = 10_000


ROBINHOOD_MAINNET = ChainConfig(
    name="robinhood",
    chain_id=4663,
    rpc_url="https://rpc.mainnet.chain.robinhood.com",
    explorer="",
)

ROBINHOOD_TESTNET = ChainConfig(
    name="robinhood-testnet",
    chain_id=46630,
    rpc_url="https://rpc.testnet.chain.robinhood.com",
    explorer="",
)

PRESETS: dict[str, ChainConfig] = {
    "robinhood": ROBINHOOD_MAINNET,
    "robinhood-testnet": ROBINHOOD_TESTNET,
}


def get_chain(name: str = "robinhood", rpc_url: str | None = None) -> ChainConfig:
    """Look up a preset, with ``CABAL_RPC_URL`` / an explicit argument winning.

    Unknown names are allowed as long as an RPC URL is supplied, so the tool is
    not limited to the presets shipped here.
    """
    preset = PRESETS.get(name)
    url = rpc_url or os.environ.get("CABAL_RPC_URL") or (preset.rpc_url if preset else "")
    if preset is None:
        if not url:
            raise ValueError(
                f"unknown chain {name!r}: pass --rpc-url or set CABAL_RPC_URL"
            )
        return ChainConfig(name=name, chain_id=0, rpc_url=url)
    if url == preset.rpc_url:
        return preset
    return ChainConfig(
        name=preset.name,
        chain_id=preset.chain_id,
        rpc_url=url,
        quote_tokens=preset.quote_tokens,
        v2_factories=preset.v2_factories,
        v3_factories=preset.v3_factories,
        infrastructure=preset.infrastructure,
        explorer=preset.explorer,
        max_block_range=preset.max_block_range,
    )
