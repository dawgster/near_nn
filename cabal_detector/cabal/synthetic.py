"""Generate a synthetic token launch with a known-cabal ground truth.

Used by the tests and by ``cabal demo``. It is a fixture, not a simulation of
any real token: it exists so the scoring pipeline can be exercised end to end
without an RPC endpoint, and so a regression in the detectors fails a test
instead of silently changing a real report.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import FundingEdge, TokenSnapshot, Transfer

BLOCK_TIME = 2
UNIT = 10 ** 18


def addr(prefix: str, index: int) -> str:
    return "0x" + (prefix * 2 + f"{index:034x}")[:40]


@dataclass
class SyntheticLaunch:
    snapshot: TokenSnapshot
    deployer: str
    pool: str
    quote: str = ""
    insiders: list[str] = field(default_factory=list)
    snipers: list[str] = field(default_factory=list)
    retail: list[str] = field(default_factory=list)

    @property
    def cabal(self) -> set[str]:
        return set(self.insiders) | set(self.snipers) | {self.deployer}


def generate_launch(
    seed: int = 7,
    *,
    token: str = "0xc0ffee0000000000000000000000000000000001",
    quote: str = "0xeeee000000000000000000000000000000000002",
    n_insiders: int = 3,
    n_snipers: int = 3,
    n_retail: int = 30,
    deploy_block: int = 1000,
    symbol: str = "CABAL",
    salt: int = 0,
) -> SyntheticLaunch:
    """One launch. ``salt`` shifts every address so separate launches get
    separate participants -- otherwise cross-token signals fire on the fixture's
    own reuse of addresses rather than on anything the detectors found."""
    rng = random.Random(seed)
    transfers: list[Transfer] = []
    funding: list[FundingEdge] = []
    counter = {"n": 0}

    def ts(block: int) -> int:
        return 1_700_000_000 + block * BLOCK_TIME

    def tx(block: int) -> str:
        counter["n"] += 1
        return f"0x{counter['n']:064x}"

    def move(token_addr: str, sender: str, recipient: str, amount: int, block: int, tx_hash: str) -> None:
        transfers.append(
            Transfer(
                token=token_addr,
                sender=sender,
                recipient=recipient,
                amount=amount,
                block=block,
                timestamp=ts(block),
                tx_hash=tx_hash,
                log_index=len([t for t in transfers if t.tx_hash == tx_hash]),
            )
        )

    base = salt * 1000
    deployer = addr("d", base + 1)
    pool = addr("9", base + 1)
    insider_funder = addr("f", base + 1)   # one operator paying gas for the ring
    exchange_hub = addr("e", base + 1)     # funds everyone; must not create a cluster
    insiders = [addr("a", base + i) for i in range(1, n_insiders + 1)]
    snipers = [addr("b", base + i) for i in range(1, n_snipers + 1)]
    retail = [addr("c", base + i) for i in range(1, n_retail + 1)]

    supply = 1_000_000_000 * UNIT

    # --- funding, before the launch --------------------------------------
    for i, wallet in enumerate([deployer, *insiders, *snipers]):
        block = deploy_block - 400 + i * 3
        funding.append(
            FundingEdge(
                sender=insider_funder,
                recipient=wallet,
                value=UNIT // 10,
                block=block,
                timestamp=ts(block),
                tx_hash=tx(block),
            )
        )
    for i, wallet in enumerate(retail):
        block = deploy_block - 2_000_000 + i * 37  # long-standing wallets
        funding.append(
            FundingEdge(
                sender=exchange_hub,
                recipient=wallet,
                value=UNIT,
                block=block,
                timestamp=ts(block),
                tx_hash=tx(block),
            )
        )

    # --- deploy and pre-liquidity allocations ----------------------------
    move(token, "0x" + "0" * 40, deployer, supply, deploy_block, tx(deploy_block))
    for i, wallet in enumerate(insiders):
        block = deploy_block + 1 + i
        move(token, deployer, wallet, int(supply * 0.04), block, tx(block))

    # --- liquidity added: the sale opens ---------------------------------
    liq_block = deploy_block + 10
    liq_tx = tx(liq_block)
    pooled_tokens = int(supply * 0.5)
    move(token, deployer, pool, pooled_tokens, liq_block, liq_tx)
    move(quote, deployer, pool, 100 * UNIT, liq_block, liq_tx)

    base_price = 100 * UNIT / pooled_tokens

    def buy(wallet: str, block: int, token_amount: int, price: float) -> None:
        tx_hash = tx(block)
        move(token, pool, wallet, token_amount, block, tx_hash)
        move(quote, wallet, pool, max(1, int(token_amount * price)), block, tx_hash)

    def sell(wallet: str, block: int, token_amount: int, price: float) -> None:
        tx_hash = tx(block)
        move(token, wallet, pool, token_amount, block, tx_hash)
        move(quote, pool, wallet, max(1, int(token_amount * price)), block, tx_hash)

    # --- snipers take the opening block ----------------------------------
    for i, wallet in enumerate(snipers):
        buy(wallet, liq_block + (i % 2), int(supply * 0.01), base_price * (1 + 0.02 * i))

    # --- retail flows in while the price climbs --------------------------
    price = base_price
    block = liq_block + 3
    for i, wallet in enumerate(retail):
        block += rng.randint(1, 6)
        price *= 1.06  # steady run-up: ~6x over the retail window
        buy(wallet, block, int(supply * rng.uniform(0.0005, 0.002)), price)

    peak_block = block + 2
    peak_price = price

    # --- the ring distributes into the top -------------------------------
    for i, wallet in enumerate(insiders):
        sell(wallet, peak_block + i, int(supply * 0.036), peak_price * 0.98)
    for i, wallet in enumerate(snipers):
        sell(wallet, peak_block + len(insiders) + i, int(supply * 0.009), peak_price * 0.95)

    # --- and a few retail wallets exit at a loss -------------------------
    for i, wallet in enumerate(retail[:5]):
        sell(wallet, peak_block + 10 + i, int(supply * 0.0004), peak_price * 0.55)

    snapshot = TokenSnapshot(
        token=token,
        chain="synthetic",
        chain_id=0,
        symbol=symbol,
        decimals=18,
        from_block=deploy_block - 2_000_000,
        to_block=peak_block + 20,
        transfers=transfers,
        funding=funding,
        pools=[pool],
        deployer=deployer,
    )
    return SyntheticLaunch(
        snapshot=snapshot,
        deployer=deployer,
        pool=pool,
        quote=quote,
        insiders=insiders,
        snipers=snipers,
        retail=retail,
    )


def generate_series(
    count: int = 3, seed: int = 7, repeat_wallets: int = 2
) -> list[SyntheticLaunch]:
    """Several launches sharing part of the same ring, for recidivism testing."""
    launches = []
    first: SyntheticLaunch | None = None
    for i in range(count):
        launch = generate_launch(
            seed=seed + i,
            token="0xc0ffee" + f"{i:034x}"[:34],
            symbol=f"CABAL{i}",
            deploy_block=1000 + i * 100_000,
            salt=i,
        )
        if first is not None and repeat_wallets:
            launch = _substitute(launch, first, repeat_wallets)
        launches.append(launch)
        if first is None:
            first = launch
    return launches


def _substitute(launch: SyntheticLaunch, first: SyntheticLaunch, n: int) -> SyntheticLaunch:
    """Rewrite some of this launch's snipers to be the previous launch's snipers."""
    mapping = dict(zip(launch.snipers[:n], first.snipers[:n]))
    if not mapping:
        return launch

    def swap(address: str) -> str:
        return mapping.get(address, address)

    snap = launch.snapshot
    snap.transfers = [
        Transfer(
            token=t.token,
            sender=swap(t.sender),
            recipient=swap(t.recipient),
            amount=t.amount,
            block=t.block,
            timestamp=t.timestamp,
            tx_hash=t.tx_hash,
            log_index=t.log_index,
        )
        for t in snap.transfers
    ]
    snap.funding = [
        FundingEdge(
            sender=swap(f.sender),
            recipient=swap(f.recipient),
            value=f.value,
            block=f.block,
            timestamp=f.timestamp,
            tx_hash=f.tx_hash,
        )
        for f in snap.funding
    ]
    launch.snipers = [swap(s) for s in launch.snipers]
    return launch
