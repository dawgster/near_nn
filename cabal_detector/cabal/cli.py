"""Command line interface.

    cabal snapshot --token 0x...        pull a launch from RPC to disk
    cabal analyze  --snapshot f.json    score wallets from one or more snapshots
    cabal demo                          run the whole pipeline on a fixture

``snapshot`` and ``analyze`` are separate on purpose: ingestion is slow and
rate-limited, scoring is not, and you will want to retune weights without
re-pulling the chain.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import analyze
from .chains import PRESETS, get_chain
from .config import DetectorConfig
from .models import AnalysisResult, TokenSnapshot, normalize
from .report import to_csv, to_json, to_markdown, to_text
from .sources.snapshot import load_snapshot, save_snapshot

FORMATS = ("text", "markdown", "json", "csv")


def _render(result: AnalysisResult, fmt: str, min_score: float, limit: int) -> str:
    if fmt == "json":
        return to_json(result)
    if fmt == "csv":
        return to_csv(result, min_score)
    if fmt == "markdown":
        return to_markdown(result, min_score, limit)
    return to_text(result, min_score, limit)


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text)
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def _read_addresses(values: list[str] | None, file: str | None) -> set[str]:
    out = {normalize(v) for v in (values or [])}
    if file:
        for line in Path(file).read_text().splitlines():
            line = line.strip().split("#")[0].strip()
            if line:
                out.add(normalize(line))
    return out


def cmd_snapshot(args: argparse.Namespace) -> int:
    from .ingest import collect_token
    from .sources.rpc import RpcSource

    chain = get_chain(args.chain, args.rpc_url)
    source = RpcSource(chain, sleep_between=args.throttle)

    def progress(msg: str) -> None:
        if not args.quiet:
            print(f"  {msg}", file=sys.stderr)

    print(f"chain {chain.name} via {chain.rpc_url}", file=sys.stderr)
    for token in args.token:
        snapshot = collect_token(
            source,
            token,
            from_block=args.from_block,
            to_block=args.to_block,
            quote_tokens=args.quote,
            pools=args.pool,
            v2_factories=args.factory_v2,
            v3_factories=args.factory_v3,
            funding_lookback=args.funding_lookback,
            with_funding=not args.no_funding,
            progress=progress,
        )
        out_dir = Path(args.out_dir)
        path = out_dir / f"{snapshot.symbol or 'token'}_{normalize(token)[:10]}.json"
        save_snapshot(snapshot, path)
        print(f"wrote {path} ({len(snapshot.transfers)} transfers, {source.calls} rpc calls)")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    config = DetectorConfig.load(args.config)
    snapshots: list[TokenSnapshot] = [load_snapshot(p) for p in args.snapshot]

    if args.token:
        from .ingest import collect_token
        from .sources.rpc import RpcSource

        chain = get_chain(args.chain, args.rpc_url)
        source = RpcSource(chain, sleep_between=args.throttle)
        for token in args.token:
            snapshots.append(
                collect_token(
                    source,
                    token,
                    from_block=args.from_block,
                    to_block=args.to_block,
                    quote_tokens=args.quote,
                    pools=args.pool,
                    with_funding=not args.no_funding,
                    progress=lambda m: print(f"  {m}", file=sys.stderr),
                )
            )

    if not snapshots:
        print("nothing to analyze: pass --snapshot and/or --token", file=sys.stderr)
        return 2

    result = analyze(
        snapshots,
        config,
        quote_tokens=_read_addresses(args.quote, None) or None,
        extra_pools=_read_addresses(args.pool, None) or None,
        ignore=_read_addresses(args.ignore, args.ignore_file),
    )
    _emit(_render(result, args.format, args.min_score, args.limit), args.out)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .synthetic import generate_series

    launches = generate_series(args.launches)
    truth = set().union(*[l.cabal for l in launches])
    result = analyze([l.snapshot for l in launches], DetectorConfig.load(args.config))
    _emit(_render(result, args.format, args.min_score, args.limit), args.out)

    if args.format in ("text", "markdown"):
        flagged = {w.wallet for w in result.wallets if w.tier in ("likely_cabal", "suspect")}
        print(
            f"\nfixture check: {len(flagged & truth)}/{len(truth)} planted wallets "
            f"flagged at suspect+, {len(flagged - truth)} false positive(s) "
            f"out of {len(result.wallets) - len(truth)} innocent wallets",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cabal",
        description="Find insider ('cabal') wallets around a token launch on "
        "Robinhood Chain or any other EVM chain.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_chain_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--chain", default="robinhood", help=f"preset: {', '.join(PRESETS)}")
        p.add_argument("--rpc-url", help="override the preset RPC URL (or set CABAL_RPC_URL)")
        p.add_argument("--throttle", type=float, default=0.0, help="seconds to sleep between RPC calls")

    def add_scan_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--from-block", type=int, help="default: binary-search the deploy block")
        p.add_argument("--to-block", type=int, help="default: latest")
        p.add_argument("--pool", action="append", default=[], help="pool address (repeatable)")
        p.add_argument("--quote", action="append", default=[], help="quote token used for pricing (repeatable)")
        p.add_argument("--no-funding", action="store_true", help="skip the native funding scan (much faster, no cluster signals)")

    def add_output_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", choices=FORMATS, default="text")
        p.add_argument("--min-score", type=float, default=25.0)
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--out", help="write to a file instead of stdout")
        p.add_argument("--config", help="JSON file overriding thresholds and weights")

    p_snap = sub.add_parser("snapshot", help="pull a token's history from RPC into a JSON file")
    add_chain_args(p_snap)
    add_scan_args(p_snap)
    p_snap.add_argument("--token", action="append", required=True, help="token address (repeatable)")
    p_snap.add_argument("--factory-v2", action="append", default=[], help="Uniswap-V2-style factory")
    p_snap.add_argument("--factory-v3", action="append", default=[], help="Uniswap-V3-style factory")
    p_snap.add_argument("--funding-lookback", type=int, default=5000, help="blocks before launch to scan for gas funding")
    p_snap.add_argument("--out-dir", default="snapshots")
    p_snap.add_argument("--quiet", action="store_true")
    p_snap.set_defaults(func=cmd_snapshot)

    p_an = sub.add_parser("analyze", help="score wallets from snapshots and/or live")
    add_chain_args(p_an)
    add_scan_args(p_an)
    add_output_args(p_an)
    p_an.add_argument("--snapshot", action="append", default=[], help="snapshot JSON (repeatable)")
    p_an.add_argument("--token", action="append", default=[], help="analyze live from RPC (repeatable)")
    p_an.add_argument("--ignore", action="append", default=[], help="address to exclude from scoring")
    p_an.add_argument("--ignore-file", help="file of addresses to exclude, one per line")
    p_an.set_defaults(func=cmd_analyze)

    p_demo = sub.add_parser("demo", help="run the pipeline on a synthetic launch with known insiders")
    add_output_args(p_demo)
    p_demo.add_argument("--launches", type=int, default=3)
    p_demo.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # surfaced as a message, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
