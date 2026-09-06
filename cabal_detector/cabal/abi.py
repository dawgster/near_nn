"""Minimal log/ABI decoding.

Only what a Transfer log and a couple of view calls need -- no eth-abi
dependency, so the tool runs anywhere Python does.
"""

from __future__ import annotations

from .keccak import event_topic, function_selector
from .models import normalize

TRANSFER_TOPIC = event_topic("Transfer(address,address,uint256)")
V2_SWAP_TOPIC = event_topic("Swap(address,uint256,uint256,uint256,uint256,address)")
V3_SWAP_TOPIC = event_topic("Swap(address,address,int256,int256,uint160,uint128,int24)")
V2_MINT_TOPIC = event_topic("Mint(address,uint256,uint256)")
V2_PAIR_CREATED_TOPIC = event_topic("PairCreated(address,address,address,uint256)")
V3_POOL_CREATED_TOPIC = event_topic("PoolCreated(address,address,uint24,int24,address)")

SWAP_TOPICS = (V2_SWAP_TOPIC, V3_SWAP_TOPIC)

DECIMALS_SELECTOR = function_selector("decimals()")
SYMBOL_SELECTOR = function_selector("symbol()")
TOKEN0_SELECTOR = function_selector("token0()")
TOKEN1_SELECTOR = function_selector("token1()")


def to_int(hexstr: str | int | None) -> int:
    if hexstr is None:
        return 0
    if isinstance(hexstr, int):
        return hexstr
    hexstr = hexstr.strip()
    if not hexstr or hexstr == "0x":
        return 0
    return int(hexstr, 16)


def to_signed(value: int, bits: int = 256) -> int:
    if value >= 1 << (bits - 1):
        return value - (1 << bits)
    return value


def data_words(data: str) -> list[str]:
    """Split a log's ``data`` field into 32-byte hex words."""
    raw = data[2:] if data.startswith("0x") else data
    return ["0x" + raw[i:i + 64] for i in range(0, len(raw) - len(raw) % 64, 64)]


def topic_to_address(topic: str) -> str:
    return normalize(topic)


def decode_transfer(log: dict) -> tuple[str, str, int] | None:
    """Decode ``Transfer(address indexed, address indexed, uint256)``.

    Returns ``None`` for the ERC-721 shape (three indexed topics, empty data),
    which shares topic0 with ERC-20 but means a token id, not an amount.
    """
    topics = log.get("topics") or []
    if len(topics) < 3 or topics[0].lower() != TRANSFER_TOPIC:
        return None
    if len(topics) >= 4:
        return None  # NFT transfer
    words = data_words(log.get("data", "0x"))
    if not words:
        return None
    return topic_to_address(topics[1]), topic_to_address(topics[2]), to_int(words[0])


def decode_string_return(data: str) -> str:
    """Decode a ``string`` return value, tolerating the bytes32 variant."""
    raw = bytes.fromhex(data[2:]) if data.startswith("0x") else bytes.fromhex(data)
    if len(raw) == 32:
        return raw.rstrip(b"\x00").decode("utf-8", "replace")
    if len(raw) < 64:
        return ""
    length = int.from_bytes(raw[32:64], "big")
    return raw[64:64 + length].decode("utf-8", "replace")
