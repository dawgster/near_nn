"""Pure-Python keccak-256.

Event topics are derived from their signature strings at import time rather than
being pasted in as magic constants, so a typo becomes a test failure instead of
a silently empty log query.
"""

_ROUNDS = 24

_ROTC = [
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
    27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
]

_PILN = [
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
    15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
]

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]

_MASK = (1 << 64) - 1


def _rotl(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (64 - shift))) & _MASK


def _keccak_f(state: list[int]) -> None:
    for rnd in range(_ROUNDS):
        # Theta
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        for x in range(5):
            d = c[(x + 4) % 5] ^ _rotl(c[(x + 1) % 5], 1)
            for y in range(0, 25, 5):
                state[y + x] ^= d

        # Rho and pi
        t = state[1]
        for i in range(24):
            j = _PILN[i]
            t, state[j] = state[j], _rotl(t, _ROTC[i])

        # Chi
        for y in range(0, 25, 5):
            row = state[y:y + 5]
            for x in range(5):
                state[y + x] = row[x] ^ ((~row[(x + 1) % 5] & _MASK) & row[(x + 2) % 5])

        # Iota
        state[0] ^= _RC[rnd]


def keccak256(data: bytes) -> bytes:
    """Return the keccak-256 digest of ``data`` (Ethereum's hash, not SHA3-256)."""
    rate = 136  # 1088 bits, the rate for keccak-256
    state = [0] * 25

    padded = bytearray(data)
    padded.append(0x01)  # keccak padding, not the 0x06 of NIST SHA3
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[i * 8:(i + 1) * 8], "little")
        _keccak_f(state)

    out = bytearray()
    for i in range(rate // 8):
        out += state[i].to_bytes(8, "little")
    return bytes(out[:32])


def event_topic(signature: str) -> str:
    """Topic0 for a canonical event signature, e.g. ``Transfer(address,address,uint256)``."""
    return "0x" + keccak256(signature.encode()).hex()


def function_selector(signature: str) -> str:
    """4-byte selector for a canonical function signature, e.g. ``decimals()``."""
    return "0x" + keccak256(signature.encode()).hex()[:8]
