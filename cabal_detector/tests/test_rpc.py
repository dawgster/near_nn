"""RPC transport behaviour, exercised against a fake session (no network)."""

import pytest

from cabal.abi import TRANSFER_TOPIC
from cabal.chains import ChainConfig, get_chain
from cabal.sources.rpc import RpcError, RpcSource


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Answers JSON-RPC batches from a handler keyed by method."""

    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def post(self, url, json=None, timeout=None):
        self.requests.append(json)
        out = []
        for req in json:
            result = self.handler(req["method"], req["params"])
            if isinstance(result, Exception):
                out.append({"id": req["id"], "error": {"message": str(result)}})
            else:
                out.append({"id": req["id"], "result": result})
        return FakeResponse(out)


def make_source(handler, **kwargs):
    chain = ChainConfig(name="test", chain_id=1, rpc_url="http://localhost", **kwargs)
    return RpcSource(chain, session=FakeSession(handler), max_retries=1)


def test_batch_matches_results_to_requests_by_id():
    source = make_source(lambda m, p: p[0])
    assert source.batch([("m", ["a"]), ("m", ["b"]), ("m", ["c"])]) == ["a", "b", "c"]


def test_rpc_error_is_raised():
    source = make_source(lambda m, p: ValueError("boom"))
    with pytest.raises(RpcError, match="boom"):
        source.call("eth_blockNumber", [])


def test_get_logs_splits_ranges_over_the_chain_limit():
    seen = []

    def handler(method, params):
        span = int(params[0]["toBlock"], 16) - int(params[0]["fromBlock"], 16) + 1
        seen.append(span)
        return []

    source = make_source(handler, max_block_range=100)
    source.get_logs(0, 999)
    assert seen and max(seen) <= 100
    assert sum(seen) == 1000, "the whole range must still be covered exactly once"


def test_get_logs_halves_the_range_when_the_node_rejects_it():
    """Public endpoints cap result counts; a rejection should narrow, not abort."""

    def handler(method, params):
        span = int(params[0]["toBlock"], 16) - int(params[0]["fromBlock"], 16) + 1
        if span > 50:
            return ValueError("query returned more than 10000 results")
        return []

    source = make_source(handler, max_block_range=1000)
    assert source.get_logs(0, 199) == []


def test_get_logs_reraises_when_a_single_block_fails():
    source = make_source(lambda m, p: ValueError("node down"), max_block_range=1000)
    with pytest.raises(RpcError):
        source.get_logs(7, 7)


def test_transfers_decode_and_carry_block_timestamps():
    token = "0x" + "c0" * 20
    log = {
        "topics": [TRANSFER_TOPIC, "0x" + "0" * 24 + "aa" * 20, "0x" + "0" * 24 + "bb" * 20],
        "data": "0x" + f"{500:064x}",
        "blockNumber": "0x10",
        "transactionHash": "0xABC",
        "logIndex": "0x2",
    }

    def handler(method, params):
        if method == "eth_getLogs":
            return [log]
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(1_700_000_000), "number": params[0]}
        return None

    source = make_source(handler, max_block_range=1000)
    transfers = source.transfers(token, 0, 100)
    assert len(transfers) == 1
    tr = transfers[0]
    assert tr.sender == "0x" + "aa" * 20
    assert tr.amount == 500
    assert tr.block == 16
    assert tr.timestamp == 1_700_000_000
    assert tr.tx_hash == "0xabc", "hashes are lowercased so they dedupe"


def test_block_timestamps_are_cached():
    calls = {"n": 0}

    def handler(method, params):
        calls["n"] += 1
        return {"timestamp": "0x1", "number": params[0]}

    source = make_source(handler)
    source.block_timestamps([1, 2, 3])
    first = calls["n"]
    source.block_timestamps([1, 2, 3])
    assert calls["n"] == first, "a cached block must not be refetched"


def test_funding_edges_only_keep_watched_addresses():
    watched = "0x" + "aa" * 20
    other = "0x" + "cc" * 20

    def handler(method, params):
        return {
            "number": params[0],
            "timestamp": "0x64",
            "transactions": [
                {"from": "0x" + "ff" * 20, "to": watched, "value": "0x64", "hash": "0x1"},
                {"from": "0x" + "ff" * 20, "to": other, "value": "0x64", "hash": "0x2"},
                {"from": "0x" + "ff" * 20, "to": watched, "value": "0x0", "hash": "0x3"},
                {"from": "0x" + "ff" * 20, "to": None, "value": "0x64", "hash": "0x4"},
            ],
        }

    source = make_source(handler)
    edges = source.funding_edges([watched], 1, 1)
    assert len(edges) == 1, "zero-value, contract-creation and unrelated txs are dropped"
    assert edges[0].recipient == watched and edges[0].value == 100


def test_funding_scan_window_is_capped():
    seen = []

    def handler(method, params):
        seen.append(int(params[0], 16))
        return {"number": params[0], "timestamp": "0x1", "transactions": []}

    source = make_source(handler)
    source.funding_edges(["0x" + "aa" * 20], 0, 10_000, max_blocks=100)
    assert len(seen) == 100, "the expensive path must respect its cap"


def test_robinhood_preset_and_rpc_override(monkeypatch):
    monkeypatch.delenv("CABAL_RPC_URL", raising=False)
    chain = get_chain("robinhood")
    assert chain.chain_id == 4663
    assert chain.rpc_url.startswith("https://")
    override = get_chain("robinhood", "http://localhost:8545")
    assert override.chain_id == 4663 and override.rpc_url == "http://localhost:8545"
    with pytest.raises(ValueError):
        get_chain("nonexistent-chain")
