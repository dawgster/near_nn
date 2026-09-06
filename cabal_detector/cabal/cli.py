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
import json
import sys
from pathlib import Path

from .analysis import analyze
from .chains import PRESETS, get_chain
from .config import DetectorConfig
from .models import AnalysisResult, TokenSnapshot, normalize
from .report import to_csv, to_json, to_markdown, to_text
from .screen import ScreenCriteria
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


def _criteria(args: argparse.Namespace) -> ScreenCriteria | None:
    """Screening rules from the flags, or ``None`` when screening is off."""
    if getattr(args, "include_duds", False):
        return None
    return ScreenCriteria(
        min_pump_multiple=args.min_pump,
        min_unique_buyers=args.min_buyers,
        min_trades=args.min_trades,
        min_quote_volume=args.min_volume,
        include_unpriced=args.include_unpriced,
    )


def _tokens_from(args: argparse.Namespace) -> list[str]:
    tokens = list(args.token or [])
    if getattr(args, "tokens_file", None):
        for line in Path(args.tokens_file).read_text().splitlines():
            line = line.strip().split("#")[0].strip()
            if line:
                tokens.append(line)
    return tokens


def cmd_snapshot(args: argparse.Namespace) -> int:
    from .ingest import collect_token
    from .sources.rpc import RpcSource

    chain = get_chain(args.chain, args.rpc_url)
    source = RpcSource(chain, sleep_between=args.throttle)

    def progress(msg: str) -> None:
        if not args.quiet:
            print(f"  {msg}", file=sys.stderr)

    tokens = _tokens_from(args)
    if not tokens:
        print("no tokens given: pass --token or --tokens-file", file=sys.stderr)
        return 2
    print(f"chain {chain.name} via {chain.rpc_url}", file=sys.stderr)
    for token in tokens:
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
        criteria=_criteria(args),
    )
    for verdict in result.rejected:
        print(
            f"screened out {verdict.symbol or verdict.token}: {'; '.join(verdict.reasons)}",
            file=sys.stderr,
        )
    _emit(_render(result, args.format, args.min_score, args.limit), args.out)
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    """Triage only: which of these tokens actually went anywhere?"""
    from .screen import screen_timeline
    from .timeline import build_timeline

    criteria = _criteria(args) or ScreenCriteria()
    quotes = _read_addresses(args.quote, None) or None
    rows = []
    for path in args.snapshot:
        snapshot = load_snapshot(path)
        timeline = build_timeline(snapshot, quote_tokens=quotes)
        rows.append(screen_timeline(timeline, criteria))
    if not rows:
        print("nothing to screen: pass --snapshot", file=sys.stderr)
        return 2

    rows.sort(key=lambda v: (v.passed, v.multiple), reverse=True)
    if args.format == "json":
        _emit(json.dumps([v.to_json() for v in rows], indent=2), args.out)
        return 0

    lines = [f"{'token':<44}{'verdict':<9}{'peak':<9}{'buyers':<8}{'trades':<8}notes",
             "-" * 100]
    for v in rows:
        lines.append(
            f"{(v.symbol or v.token)[:42]:<44}{'PASS' if v.passed else 'skip':<9}"
            f"{v.multiple:<9.2f}{v.unique_buyers:<8}{v.trades:<8}{'; '.join(v.reasons)}"
        )
    passed = [v for v in rows if v.passed]
    lines.append("")
    lines.append(f"{len(passed)}/{len(rows)} token(s) worth analyzing")
    _emit("\n".join(lines), args.out)

    if args.write_tokens:
        Path(args.write_tokens).write_text("\n".join(v.token for v in passed) + "\n")
        print(f"wrote {len(passed)} token address(es) to {args.write_tokens}", file=sys.stderr)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """Sweep a block range for launches and keep only the ones that ran."""
    from .discover import discover_pumped_tokens
    from .sources.rpc import RpcSource

    chain = get_chain(args.chain, args.rpc_url)
    source = RpcSource(chain, sleep_between=args.throttle)
    to_block = args.to_block if args.to_block is not None else source.block_number()
    from_block = args.from_block
    if from_block is None:
        from_block = max(0, to_block - args.lookback)

    print(f"chain {chain.name}: scanning blocks {from_block}..{to_block}", file=sys.stderr)
    candidates = discover_pumped_tokens(
        source,
        from_block,
        to_block,
        v2_factories=args.factory_v2 or chain.v2_factories,
        v3_factories=args.factory_v3 or chain.v3_factories,
        quote_tokens=args.quote,
        criteria=_criteria(args) or ScreenCriteria(),
        max_tokens=args.max_tokens,
        progress=lambda m: print(f"  {m}", file=sys.stderr),
    )
    if not candidates:
        print(
            "no launches found: check --factory-v2/--factory-v3 for this chain's DEX",
            file=sys.stderr,
        )
        return 1

    passed = [c for c in candidates if c.verdict and c.verdict.passed]
    if args.format == "json":
        _emit(
            json.dumps(
                [
                    {"token": c.token, "quote": c.quote, "pools": c.pools,
                     **(c.verdict.to_json() if c.verdict else {})}
                    for c in candidates
                ],
                indent=2,
            ),
            args.out,
        )
    else:
        lines = [f"{'token':<44}{'verdict':<9}{'peak':<9}{'buyers':<8}notes", "-" * 100]
        for c in candidates:
            v = c.verdict
            lines.append(
                f"{(v.symbol or c.token)[:42]:<44}{'PASS' if v.passed else 'skip':<9}"
                f"{v.multiple:<9.2f}{v.unique_buyers:<8}{'; '.join(v.reasons)}"
            )
        lines.append("")
        lines.append(f"{len(passed)}/{len(candidates)} launch(es) actually pumped")
        _emit("\n".join(lines), args.out)

    if args.write_tokens:
        Path(args.write_tokens).write_text("\n".join(c.token for c in passed) + "\n")
        print(
            f"wrote {len(passed)} token address(es) to {args.write_tokens} — "
            f"feed it to `cabal snapshot --tokens-file`",
            file=sys.stderr,
        )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .synthetic import generate_series

    from .synthetic import generate_dud

    launches = generate_series(args.launches)
    truth = set().union(*[l.cabal for l in launches])
    # One launch that goes nowhere, to show the screen dropping it.
    dud = generate_dud()
    snapshots = [l.snapshot for l in launches] + [dud.snapshot]
    result = analyze(
        snapshots, DetectorConfig.load(args.config), criteria=_criteria(args)
    )
    _emit(_render(result, args.format, args.min_score, args.limit), args.out)

    if args.format in ("text", "markdown"):
        flagged = {w.wallet for w in result.wallets if w.tier in ("likely_cabal", "suspect")}
        print(
            f"\nfixture check: {len(flagged & truth)}/{len(truth)} planted wallets "
            f"flagged at suspect+, {len(flagged - truth)} false positive(s) "
            f"out of {len(result.wallets) - len(truth)} innocent wallets",
            file=sys.stderr,
        )
        leaked = len(dud.cabal & {w.wallet for w in result.wallets})
        print(
            f"screen: {len(result.rejected)} dud token(s) dropped, "
            f"{leaked} of their wallets in the report",
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

    def add_screen_args(p: argparse.ArgumentParser) -> None:
        g = p.add_argument_group(
            "pump screen",
            "Only analyze coins that actually went somewhere. A launch that "
            "never ran has no cabal worth naming.",
        )
        g.add_argument("--min-pump", type=float, default=3.0, help="minimum peak multiple over the launch price (default 3x)")
        g.add_argument("--min-buyers", type=int, default=25, help="minimum unique buyers (default 25)")
        g.add_argument("--min-trades", type=int, default=20, help="minimum trades (default 20)")
        g.add_argument("--min-volume", type=int, default=0, help="minimum quote volume in raw units (default off)")
        g.add_argument("--include-unpriced", action="store_true", help="keep tokens whose price could not be reconstructed")
        g.add_argument("--include-duds", action="store_true", help="disable the screen and analyze every token")

    def add_output_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", choices=FORMATS, default="text")
        p.add_argument("--min-score", type=float, default=25.0)
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--out", help="write to a file instead of stdout")
        p.add_argument("--config", help="JSON file overriding thresholds and weights")

    p_snap = sub.add_parser("snapshot", help="pull a token's history from RPC into a JSON file")
    add_chain_args(p_snap)
    add_scan_args(p_snap)
    p_snap.add_argument("--token", action="append", default=[], help="token address (repeatable)")
    p_snap.add_argument("--tokens-file", help="file of token addresses, one per line (e.g. from `cabal discover`)")
    p_snap.add_argument("--factory-v2", action="append", default=[], help="Uniswap-V2-style factory")
    p_snap.add_argument("--factory-v3", action="append", default=[], help="Uniswap-V3-style factory")
    p_snap.add_argument("--funding-lookback", type=int, default=5000, help="blocks before launch to scan for gas funding")
    p_snap.add_argument("--out-dir", default="snapshots")
    p_snap.add_argument("--quiet", action="store_true")
    p_snap.set_defaults(func=cmd_snapshot)

    p_an = sub.add_parser("analyze", help="score wallets from snapshots and/or live")
    add_chain_args(p_an)
    add_scan_args(p_an)
    add_screen_args(p_an)
    add_output_args(p_an)
    p_an.add_argument("--snapshot", action="append", default=[], help="snapshot JSON (repeatable)")
    p_an.add_argument("--token", action="append", default=[], help="analyze live from RPC (repeatable)")
    p_an.add_argument("--tokens-file", help="file of token addresses to analyze live, one per line")
    p_an.add_argument("--ignore", action="append", default=[], help="address to exclude from scoring")
    p_an.add_argument("--ignore-file", help="file of addresses to exclude, one per line")
    p_an.set_defaults(func=cmd_analyze)

    p_screen = sub.add_parser(
        "screen", help="triage snapshots: which coins actually pumped?"
    )
    add_screen_args(p_screen)
    p_screen.add_argument("--snapshot", action="append", default=[], required=True, help="snapshot JSON (repeatable)")
    p_screen.add_argument("--quote", action="append", default=[], help="quote token used for pricing (repeatable)")
    p_screen.add_argument("--format", choices=("text", "json"), default="text")
    p_screen.add_argument("--out", help="write to a file instead of stdout")
    p_screen.add_argument("--write-tokens", help="write the passing token addresses to this file")
    p_screen.set_defaults(func=cmd_screen)

    p_disc = sub.add_parser(
        "discover",
        help="sweep a block range for launches and keep the ones that pumped",
    )
    add_chain_args(p_disc)
    add_screen_args(p_disc)
    p_disc.add_argument("--factory-v2", action="append", default=[], help="Uniswap-V2-style factory (repeatable)")
    p_disc.add_argument("--factory-v3", action="append", default=[], help="Uniswap-V3-style factory (repeatable)")
    p_disc.add_argument("--quote", action="append", default=[], help="quote token; inferred from pool composition if omitted")
    p_disc.add_argument("--from-block", type=int, help="default: to-block minus --lookback")
    p_disc.add_argument("--to-block", type=int, help="default: latest")
    p_disc.add_argument("--lookback", type=int, default=200_000, help="blocks to look back when --from-block is omitted")
    p_disc.add_argument("--max-tokens", type=int, default=100, help="cap how many candidates get priced")
    p_disc.add_argument("--format", choices=("text", "json"), default="text")
    p_disc.add_argument("--out", help="write to a file instead of stdout")
    p_disc.add_argument("--write-tokens", help="write the passing token addresses to this file")
    p_disc.set_defaults(func=cmd_discover)

    p_demo = sub.add_parser("demo", help="run the pipeline on a synthetic launch with known insiders")
    add_output_args(p_demo)
    add_screen_args(p_demo)
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
