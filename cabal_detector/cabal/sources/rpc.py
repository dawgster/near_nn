"""JSON-RPC ingestion for any EVM chain (Robinhood Chain by default).

Design notes:

* Log ranges are split adaptively. Public endpoints disagree about how many
  blocks or results a single ``eth_getLogs`` may return, so a failure halves the
  range and retries rather than aborting the run.
* Block timestamps are batched and cached; they dominate call count otherwise.
* Native funding edges come from full-block scans over a bounded window. There is
  no log for a plain value transfer, so this is the only way to build the funding
  graph without a tracing or explorer API.
"""

from __future__ import annotations

import itertools
import time
from typing import Any, Iterable, Sequence

import requests

from ..abi import (
    DECIMALS_SELECTOR,
    SYMBOL_SELECTOR,
    TOKEN0_SELECTOR,
    TOKEN1_SELECTOR,
    TRANSFER_TOPIC,
    V2_PAIR_CREATED_TOPIC,
    V3_POOL_CREATED_TOPIC,
    decode_string_return,
    decode_transfer,
    to_int,
    topic_to_address,
)
from ..chains import ChainConfig, get_chain
from ..models import FundingEdge, Transfer, dedupe_transfers, normalize


class RpcError(RuntimeError):
    pass


def _address_topic(address: str) -> str:
    return "0x" + normalize(address)[2:].rjust(64, "0")


class RpcSource:
    def __init__(
        self,
        chain: ChainConfig | str = "robinhood",
        rpc_url: str | None = None,
        *,
        session: requests.Session | None = None,
        timeout: int = 45,
        max_retries: int = 4,
        sleep_between: float = 0.0,
    ) -> None:
        self.chain = chain if isinstance(chain, ChainConfig) else get_chain(chain, rpc_url)
        if rpc_url and self.chain.rpc_url != rpc_url:
            self.chain = get_chain(self.chain.name, rpc_url)
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep_between = sleep_between
        self._ids = itertools.count(1)
        self._timestamps: dict[int, int] = {}
        self.calls = 0

    # ---------------------------------------------------------------- transport

    def call(self, method: str, params: list[Any]) -> Any:
        return self.batch([(method, params)])[0]

    def batch(self, requests_: Sequence[tuple[str, list[Any]]]) -> list[Any]:
        """Send a JSON-RPC batch, retrying transport errors with backoff."""
        if not requests_:
            return []
        payload = [
            {"jsonrpc": "2.0", "id": next(self._ids), "method": m, "params": p}
            for m, p in requests_
        ]
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self.calls += len(payload)
                resp = self.session.post(
                    self.chain.rpc_url, json=payload, timeout=self.timeout
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise RpcError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                body = resp.json()
                if isinstance(body, dict):
                    body = [body]
                by_id = {item.get("id"): item for item in body}
                out: list[Any] = []
                for req in payload:
                    item = by_id.get(req["id"])
                    if item is None:
                        raise RpcError(f"no response for id {req['id']}")
                    if "error" in item and item["error"]:
                        raise RpcError(
                            f"{req['method']}: {item['error'].get('message', item['error'])}"
                        )
                    out.append(item.get("result"))
                if self.sleep_between:
                    time.sleep(self.sleep_between)
                return out
            except Exception as exc:  # noqa: BLE001 - retried below, re-raised at the end
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(delay)
                delay *= 2
        raise RpcError(f"RPC call failed after {self.max_retries} attempts: {last_error}")

    # ------------------------------------------------------------------ helpers

    def chain_id(self) -> int:
        return to_int(self.call("eth_chainId", []))

    def block_number(self) -> int:
        return to_int(self.call("eth_blockNumber", []))

    def eth_call(self, to: str, data: str, block: str = "latest") -> str:
        return self.call("eth_call", [{"to": to, "data": data}, block]) or "0x"

    def token_metadata(self, token: str) -> tuple[str, int]:
        """Best-effort ``(symbol, decimals)``; non-conforming tokens fall back."""
        symbol, decimals = "", 18
        try:
            raw = self.eth_call(token, SYMBOL_SELECTOR)
            symbol = decode_string_return(raw) if raw and raw != "0x" else ""
        except Exception:
            pass
        try:
            raw = self.eth_call(token, DECIMALS_SELECTOR)
            if raw and raw != "0x":
                decimals = to_int(raw)
        except Exception:
            pass
        return symbol, min(decimals, 36)

    def pool_tokens(self, pool: str) -> tuple[str, str] | None:
        try:
            t0 = self.eth_call(pool, TOKEN0_SELECTOR)
            t1 = self.eth_call(pool, TOKEN1_SELECTOR)
        except Exception:
            return None
        if not t0 or not t1 or t0 == "0x" or t1 == "0x":
            return None
        return topic_to_address(t0), topic_to_address(t1)

    def block_timestamps(self, blocks: Iterable[int]) -> dict[int, int]:
        """Fetch (and cache) timestamps for the given block numbers."""
        wanted = sorted({b for b in blocks if b not in self._timestamps})
        for chunk in _chunks(wanted, 100):
            results = self.batch(
                [("eth_getBlockByNumber", [hex(b), False]) for b in chunk]
            )
            for block, result in zip(chunk, results):
                if result:
                    self._timestamps[block] = to_int(result.get("timestamp"))
        return self._timestamps

    # --------------------------------------------------------------------- logs

    def get_logs(
        self,
        from_block: int,
        to_block: int,
        *,
        address: str | list[str] | None = None,
        topics: list[Any] | None = None,
    ) -> list[dict]:
        """``eth_getLogs`` with adaptive range splitting."""
        out: list[dict] = []
        pending = [(from_block, to_block)]
        while pending:
            lo, hi = pending.pop()
            if lo > hi:
                continue
            span = hi - lo + 1
            if span > self.chain.max_block_range:
                mid = lo + span // 2
                pending.append((mid, hi))
                pending.append((lo, mid - 1))
                continue
            params: dict[str, Any] = {"fromBlock": hex(lo), "toBlock": hex(hi)}
            if address:
                params["address"] = address
            if topics:
                params["topics"] = topics
            try:
                out.extend(self.call("eth_getLogs", [params]) or [])
            except RpcError:
                if lo == hi:
                    raise
                mid = lo + span // 2
                pending.append((mid, hi))
                pending.append((lo, mid - 1))
        return out

    def transfers(
        self,
        token: str,
        from_block: int,
        to_block: int,
        *,
        topics_extra: list[Any] | None = None,
    ) -> list[Transfer]:
        token = normalize(token)
        topics: list[Any] = [TRANSFER_TOPIC]
        if topics_extra:
            topics.extend(topics_extra)
        logs = self.get_logs(from_block, to_block, address=token, topics=topics)
        blocks = {to_int(log["blockNumber"]) for log in logs}
        stamps = self.block_timestamps(blocks)
        result: list[Transfer] = []
        for log in logs:
            decoded = decode_transfer(log)
            if decoded is None:
                continue
            sender, recipient, amount = decoded
            block = to_int(log["blockNumber"])
            result.append(
                Transfer(
                    token=token,
                    sender=sender,
                    recipient=recipient,
                    amount=amount,
                    block=block,
                    timestamp=stamps.get(block, 0),
                    tx_hash=(log.get("transactionHash") or "").lower(),
                    log_index=to_int(log.get("logIndex")),
                )
            )
        return dedupe_transfers(result)

    def quote_legs(
        self,
        quote_tokens: Sequence[str],
        pools: Sequence[str],
        from_block: int,
        to_block: int,
    ) -> list[Transfer]:
        """Transfers of the quote asset in and out of the given pools.

        These supply the price side of each trade. Queried per pool with an
        indexed topic filter so the result set stays small.
        """
        out: list[Transfer] = []
        for quote in quote_tokens:
            for pool in pools:
                topic = _address_topic(pool)
                out.extend(self.transfers(quote, from_block, to_block, topics_extra=[None, topic]))
                out.extend(self.transfers(quote, from_block, to_block, topics_extra=[topic]))
        return dedupe_transfers(out)

    # ------------------------------------------------------------------- discovery

    def find_pools_from_factories(
        self,
        token: str,
        from_block: int,
        to_block: int,
        v2_factories: Sequence[str] = (),
        v3_factories: Sequence[str] = (),
    ) -> list[str]:
        """Pools created for ``token`` by the configured factories."""
        token_topic = _address_topic(token)
        pools: set[str] = set()
        for factory in v2_factories:
            for slot in (1, 2):
                topics: list[Any] = [V2_PAIR_CREATED_TOPIC, None, None]
                topics[slot] = token_topic
                for log in self.get_logs(from_block, to_block, address=factory, topics=topics):
                    words = log.get("data", "0x")
                    pools.add(topic_to_address(words[:66]))
        for factory in v3_factories:
            for slot in (1, 2):
                topics = [V3_POOL_CREATED_TOPIC, None, None, None]
                topics[slot] = token_topic
                for log in self.get_logs(from_block, to_block, address=factory, topics=topics):
                    data = log.get("data", "0x")
                    # (int24 tickSpacing, address pool) -- pool is the second word
                    pools.add(topic_to_address("0x" + data[2:][64:128]))
        pools.discard(normalize("0x" + "0" * 40))
        return sorted(pools)

    def find_deploy_block(self, token: str, low: int = 0, high: int | None = None) -> int:
        """Binary-search the first block where the contract has code.

        Needs an archive endpoint. Callers treat a failure as "unknown" and fall
        back to the earliest transfer seen, so this is an optimization, not a
        requirement.
        """
        if high is None:
            high = self.block_number()
        try:
            if to_int_len(self.call("eth_getCode", [token, hex(low)])) > 0:
                return low
            if to_int_len(self.call("eth_getCode", [token, hex(high)])) == 0:
                return high
        except RpcError:
            return low
        while low < high:
            mid = (low + high) // 2
            try:
                code = self.call("eth_getCode", [token, hex(mid)])
            except RpcError:
                return low
            if to_int_len(code) > 0:
                high = mid
            else:
                low = mid + 1
        return low

    # --------------------------------------------------------------- native value

    def funding_edges(
        self,
        addresses: Iterable[str],
        from_block: int,
        to_block: int,
        *,
        batch_size: int = 25,
        max_blocks: int = 20_000,
    ) -> list[FundingEdge]:
        """Scan full blocks for native transfers touching ``addresses``.

        Value transfers emit no logs, so the funding graph has to come from block
        bodies. The window is capped because this is the expensive call path;
        widen ``max_blocks`` only against a dedicated endpoint.
        """
        watch = {normalize(a) for a in addresses}
        if not watch or to_block < from_block:
            return []
        if to_block - from_block + 1 > max_blocks:
            from_block = to_block - max_blocks + 1
        edges: list[FundingEdge] = []
        for chunk in _chunks(range(from_block, to_block + 1), batch_size):
            blocks = self.batch([("eth_getBlockByNumber", [hex(b), True]) for b in chunk])
            for block in blocks:
                if not block:
                    continue
                timestamp = to_int(block.get("timestamp"))
                number = to_int(block.get("number"))
                for tx in block.get("transactions") or []:
                    to_addr = tx.get("to")
                    if not to_addr:
                        continue
                    recipient = normalize(to_addr)
                    sender = normalize(tx.get("from", ""))
                    value = to_int(tx.get("value"))
                    if value <= 0:
                        continue
                    if recipient in watch or sender in watch:
                        edges.append(
                            FundingEdge(
                                sender=sender,
                                recipient=recipient,
                                value=value,
                                block=number,
                                timestamp=timestamp,
                                tx_hash=(tx.get("hash") or "").lower(),
                            )
                        )
        return edges


def to_int_len(code: str | None) -> int:
    if not code or code == "0x":
        return 0
    return len(code) - 2


def _chunks(seq: Iterable[int], size: int) -> Iterable[list[int]]:
    it = iter(seq)
    while True:
        chunk = list(itertools.islice(it, size))
        if not chunk:
            return
        yield chunk
