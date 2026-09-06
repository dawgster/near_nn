from cabal.models import Transfer
from cabal.synthetic import generate_launch
from cabal.timeline import build_timeline, build_trades, detect_pumps, infer_pools

POOL = "0x" + "99" * 20
TOKEN = "0x" + "c0" * 20
QUOTE = "0x" + "ee" * 20
ALICE = "0x" + "a1" * 20
ROUTER = "0x" + "77" * 20


def t(sender, recipient, amount, block, tx, token=TOKEN, log_index=0):
    return Transfer(
        token=token,
        sender=sender,
        recipient=recipient,
        amount=amount,
        block=block,
        timestamp=1_700_000_000 + block * 2,
        tx_hash=tx,
        log_index=log_index,
    )


def test_infer_pools_from_two_way_flow():
    transfers = []
    for i in range(6):
        wallet = f"0x{i:040x}"
        transfers.append(t(POOL, wallet, 100, 10 + i, f"0x{i:064x}"))
        transfers.append(t(wallet, POOL, 50, 30 + i, f"0x{i + 100:064x}"))
    pools = infer_pools(transfers, TOKEN)
    assert POOL in pools


def test_build_trades_prices_from_quote_leg():
    transfers = [
        t(POOL, ALICE, 1000, 10, "0xtx1"),
        t(ALICE, POOL, 20, 10, "0xtx1", token=QUOTE, log_index=1),
    ]
    trades = build_trades(transfers, TOKEN, {POOL}, {QUOTE})
    assert len(trades) == 1
    trade = trades[0]
    assert trade.wallet == ALICE and trade.is_buy
    assert trade.quote_amount == 20
    assert trade.price == 20 / 1000


def test_router_hop_is_attributed_to_the_end_wallet():
    """pool -> router -> wallet must credit the wallet, not the router."""
    transfers = [
        t(POOL, ROUTER, 1000, 10, "0xtx1"),
        t(ROUTER, ALICE, 1000, 10, "0xtx1", log_index=1),
        t(ALICE, POOL, 20, 10, "0xtx1", token=QUOTE, log_index=2),
    ]
    trades = build_trades(transfers, TOKEN, {POOL}, {QUOTE})
    assert [tr.wallet for tr in trades] == [ALICE]


def test_detect_pumps_finds_runup_and_extends_past_the_peak():
    from cabal.models import Trade

    def trade(ts, price):
        return Trade(
            wallet=ALICE, pool=POOL, token_delta=1000,
            quote_amount=int(1000 * price), block=ts, timestamp=ts, tx_hash="0x",
        )

    # 1x -> 8x -> partial retrace; the window must cover the way down too.
    prices = [1, 1, 2, 4, 8, 7, 6, 5]
    pumps = detect_pumps([trade(1000 + i * 10, p) for i, p in enumerate(prices)])
    assert len(pumps) == 1
    assert pumps[0].multiple >= 3
    assert pumps[0].end_ts > pumps[0].peak_ts


def test_flat_price_yields_no_pump():
    from cabal.models import Trade

    trades = [
        Trade(ALICE, POOL, 1000, 1000, i, 1000 + i * 10, "0x") for i in range(20)
    ]
    assert detect_pumps(trades) == []


def test_timeline_anchors_on_the_fixture():
    launch = generate_launch()
    tl = build_timeline(launch.snapshot, quote_tokens={launch.quote})
    assert tl.deployer == launch.deployer
    assert launch.pool in tl.pools
    # deploy < allocations < liquidity <= first public trade
    assert tl.deploy_block < tl.liquidity_block <= tl.first_trade_block
    assert tl.pumps and tl.pumps[0].multiple > 3
    assert len(tl.buy_order) >= 30


def test_empty_snapshot_warns_instead_of_crashing():
    from cabal.models import TokenSnapshot

    tl = build_timeline(TokenSnapshot(token=TOKEN))
    assert tl.warnings and "no transfers" in tl.warnings[0]
