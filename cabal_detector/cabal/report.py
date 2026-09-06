"""Output formats: markdown for humans, CSV for spreadsheets, JSON for pipelines."""

from __future__ import annotations

import csv
import io
import json

from .models import AnalysisResult

DISCLAIMER = (
    "These are heuristic flags built from public on-chain data, not proof of "
    "wrongdoing. Market makers, launch-partner wallets, CEX hot wallets and "
    "ordinary fast bots all trip some of these signals. Verify every hit on an "
    "explorer before acting on it."
)


def to_json(result: AnalysisResult, indent: int = 2) -> str:
    return json.dumps(result.to_json(), indent=indent)


def to_csv(result: AnalysisResult, min_score: float = 0.0) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["wallet", "score", "tier", "cluster_id", "tokens", "signals", "top_reason"])
    for w in result.flagged(min_score):
        writer.writerow(
            [
                w.wallet,
                f"{w.score:.2f}",
                w.tier,
                w.cluster_id if w.cluster_id is not None else "",
                "|".join(w.tokens),
                "|".join(s.name for s in sorted(w.signals, key=lambda s: -s.contribution)),
                w.reasons[0] if w.reasons else "",
            ]
        )
    return buf.getvalue()


def _screen_lines(result: AnalysisResult) -> list[str]:
    if not result.screened:
        return []
    lines = ["## Pump screen", ""]
    lines.append("| Token | Verdict | Peak | Buyers | Trades | Notes |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for v in sorted(result.screened, key=lambda v: (v.passed, v.multiple), reverse=True):
        lines.append(
            f"| `{v.symbol or v.token}` | {'analyzed' if v.passed else 'skipped'} | "
            f"{v.multiple:.2f}x | {v.unique_buyers} | {v.trades} | {'; '.join(v.reasons)} |"
        )
    passed = sum(1 for v in result.screened if v.passed)
    lines.append("")
    lines.append(
        f"_{passed} of {len(result.screened)} token(s) cleared the screen; wallets "
        f"below come only from those._"
    )
    lines.append("")
    return lines


def to_markdown(result: AnalysisResult, min_score: float = 0.0, limit: int = 50) -> str:
    lines: list[str] = ["# Cabal wallet report", ""]
    lines.extend(_screen_lines(result))

    for token, tl in result.timelines.items():
        lines.append(f"## Token `{tl.get('symbol') or token}` (`{token}`)")
        lines.append("")
        lines.append(f"- deployer: `{tl.get('deployer') or 'unknown'}`")
        lines.append(f"- deploy block: {tl.get('deploy_block')}")
        lines.append(f"- liquidity block: {tl.get('liquidity_block')}")
        lines.append(f"- first public trade block: {tl.get('first_trade_block')}")
        lines.append(f"- pools: {', '.join(f'`{p}`' for p in tl.get('pools', [])) or 'none identified'}")
        lines.append(f"- buyers seen: {tl.get('buyers')} across {tl.get('trades')} trades")
        pumps = tl.get("pumps") or []
        if pumps:
            for p in pumps:
                lines.append(
                    f"- pump: {p['multiple']}x over {p['duration_s'] / 60:.0f} min "
                    f"(start ts {p['start_ts']})"
                )
        else:
            lines.append("- pump: none detected")
        lines.append("")

    flagged = result.flagged(min_score)[:limit]
    lines.append(f"## Flagged wallets ({len(flagged)} shown)")
    lines.append("")
    if not flagged:
        lines.append("_No wallet cleared the score threshold._")
    else:
        lines.append("| # | Wallet | Score | Tier | Cluster | Why |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for i, w in enumerate(flagged, 1):
            reason = w.reasons[0] if w.reasons else ""
            cluster = f"C{w.cluster_id}" if w.cluster_id is not None else "—"
            lines.append(
                f"| {i} | `{w.wallet}` | {w.score:.0f} | {w.tier} | {cluster} | {reason} |"
            )
    lines.append("")

    if result.clusters:
        lines.append("## Clusters")
        lines.append("")
        for c in result.clusters:
            lines.append(f"### Cluster C{c.cluster_id} — {len(c.members)} wallets, score {c.score:.0f}")
            for reason in c.reasons:
                lines.append(f"- {reason}")
            for member in c.members:
                lines.append(f"  - `{member}`")
            lines.append("")

    detailed = [w for w in flagged if len(w.signals) > 1][:20]
    if detailed:
        lines.append("## Evidence")
        lines.append("")
        for w in detailed:
            lines.append(f"### `{w.wallet}` — {w.score:.0f} ({w.tier})")
            for s in sorted(w.signals, key=lambda s: -s.contribution):
                lines.append(f"- **{s.name}** ({s.contribution:.2f}): {s.detail}")
            lines.append("")

    if result.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in dict.fromkeys(result.warnings):
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def to_text(result: AnalysisResult, min_score: float = 0.0, limit: int = 50) -> str:
    rows = result.flagged(min_score)[:limit]
    header: list[str] = []
    if result.screened:
        passed = sum(1 for v in result.screened if v.passed)
        header.append(
            f"pump screen: {passed}/{len(result.screened)} token(s) analyzed, "
            f"{len(result.screened) - passed} skipped as duds"
        )
        for v in result.rejected:
            header.append(f"  skipped {v.symbol or v.token}: {'; '.join(v.reasons)}")
        header.append("")
    width = 4 + 44 + 8 + 15 + 9
    out = header + [
        f"{'#':<4}{'wallet':<44}{'score':<8}{'tier':<15}{'cluster':<9}reasons",
        "-" * (width + 8),
    ]
    for i, w in enumerate(rows, 1):
        cluster = f"C{w.cluster_id}" if w.cluster_id is not None else "-"
        out.append(
            f"{i:<4}{w.wallet:<44}{w.score:<8.0f}{w.tier:<15}{cluster:<9}"
            f"{w.reasons[0] if w.reasons else ''}"
        )
        for reason in w.reasons[1:4]:
            out.append(" " * 80 + reason)
    if not rows:
        out.append("(no wallet cleared the score threshold)")
    out.append("")
    out.append(DISCLAIMER)
    return "\n".join(out)
