"""The event topics are derived, not pasted, so pin them to known-good values."""

from cabal.abi import (
    DECIMALS_SELECTOR,
    SYMBOL_SELECTOR,
    TOKEN0_SELECTOR,
    TRANSFER_TOPIC,
    V2_PAIR_CREATED_TOPIC,
    V2_SWAP_TOPIC,
    V3_POOL_CREATED_TOPIC,
    V3_SWAP_TOPIC,
    decode_transfer,
    to_signed,
)
from cabal.keccak import keccak256


def test_keccak_vectors():
    assert keccak256(b"").hex() == (
        "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    )
    assert keccak256(b"abc").hex() == (
        "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    )
    # Longer than the 136-byte rate, so this exercises multi-block absorption.
    assert len(keccak256(b"x" * 500)) == 32


def test_known_topics_and_selectors():
    assert TRANSFER_TOPIC == (
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    )
    assert V2_SWAP_TOPIC == (
        "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
    )
    assert V3_SWAP_TOPIC == (
        "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
    )
    assert V2_PAIR_CREATED_TOPIC == (
        "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
    )
    assert V3_POOL_CREATED_TOPIC == (
        "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
    )
    assert DECIMALS_SELECTOR == "0x313ce567"
    assert SYMBOL_SELECTOR == "0x95d89b41"
    assert TOKEN0_SELECTOR == "0x0dfe1681"


def _topic(addr_byte: str) -> str:
    return "0x" + "0" * 24 + addr_byte * 20


def test_decode_erc20_transfer():
    log = {
        "topics": [TRANSFER_TOPIC, _topic("aa"), _topic("bb")],
        "data": "0x" + f"{12345:064x}",
    }
    assert decode_transfer(log) == ("0x" + "aa" * 20, "0x" + "bb" * 20, 12345)


def test_decode_skips_nft_transfer():
    """ERC-721 shares topic0 but the third topic is a token id, not an amount."""
    log = {
        "topics": [TRANSFER_TOPIC, _topic("aa"), _topic("bb"), "0x" + f"{7:064x}"],
        "data": "0x",
    }
    assert decode_transfer(log) is None


def test_to_signed():
    assert to_signed(1) == 1
    assert to_signed((1 << 256) - 1) == -1
