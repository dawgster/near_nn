"""The pump screen: only coins that actually ran should reach wallet scoring."""

from cabal.analysis import analyze, analyze_token
from cabal.discover import build_candidates, infer_quote_tokens
from cabal.screen import ScreenCriteria, screen_timeline
from cabal.synthetic import generate_dud, generate_launch
from cabal.timeline import build_timeline

QUOTE = "0x" + "ee" * 20
WETH = "0x" + "22" * 20


def verdict_for(launch, criteria=None):
    timeline = build_timeline(launch.snapshot, quote_tokens={launch.quote})
    return screen_timeline(timeline, criteria)


def test_a_runner_passes_and_a_dud_fails():
    assert verdict_for(generate_launch()).passed
    dud = verdict_for(generate_dud())
    assert not dud.passed
    assert "below the 3x floor" in dud.reasons[0]
    assert dud.multiple < 2


def test_multiple_is_reported_even_when_rejected():
    """A skip should say how far it got, not just that it failed."""
    v = verdict_for(generate_dud())
    assert v.priced and v.multiple > 0
    assert v.unique_buyers > 0 and v.trades > 0


def test_thin_book_is_rejected_despite_a_big_multiple():
    """Four trades between two wallets can print any multiple you like."""
    launch = generate_launch(n_retail=3, n_snipers=1, n_insiders=1)
    v = verdict_for(launch, ScreenCriteria(min_pump_multiple=1.0, min_unique_buyers=25))
    assert not v.passed
    assert any("unique buyers" in r for r in v.reasons)


def test_unpriced_token_is_skipped_unless_opted_in():
    launch = generate_launch()
    # Drop the quote-side transfers, so no price can be reconstructed.
    launch.snapshot.transfers = [
        t for t in launch.snapshot.transfers if t.token != launch.quote
    ]
    timeline = build_timeline(launch.snapshot, quote_tokens={launch.quote})

    strict = screen_timeline(timeline, ScreenCriteria())
    assert not strict.passed and "no price series" in strict.reasons[0]

    lenient = screen_timeline(timeline, ScreenCriteria(include_unpriced=True))
    assert lenient.passed
    assert any("unpriced" in r for r in lenient.reasons)


def test_screened_out_token_contributes_no_wallets():
    runner, dud = generate_launch(), generate_dud()
    assert not (runner.cabal & dud.cabal), "fixtures must have distinct participants"

    result = analyze([runner.snapshot, dud.snapshot], criteria=ScreenCriteria())
    flagged = {w.wallet for w in result.wallets}

    assert not (dud.cabal & flagged), "a dud's wallets must not be named"
    assert runner.cabal <= flagged
    assert result.tokens == [runner.snapshot.token]
    assert len(result.rejected) == 1


def test_screen_off_analyzes_everything():
    runner, dud = generate_launch(), generate_dud()
    result = analyze([runner.snapshot, dud.snapshot], criteria=None)
    flagged = {w.wallet for w in result.wallets}
    assert dud.cabal <= flagged
    assert len(result.tokens) == 2
    assert result.screened == []


def test_rejected_token_skips_the_scoring_work():
    """A screened-out token should not build activity or clusters at all."""
    analysis = analyze_token(generate_dud().snapshot, criteria=ScreenCriteria())
    assert analysis.verdict is not None and not analysis.verdict.passed
    assert analysis.signals == {}
    assert analysis.clusters == []
    assert analysis.context.activity == {}


def test_recidivism_counts_only_screened_tokens():
    """Being early on winners is the signal; duds must not pad the count."""
    from cabal.synthetic import generate_series

    launches = generate_series(3)
    dud = generate_dud()
    # Put a repeat wallet into the dud as well; it must not raise the count.
    result = analyze(
        [l.snapshot for l in launches] + [dud.snapshot], criteria=ScreenCriteria()
    )
    for wallet in result.wallets:
        assert dud.snapshot.symbol not in wallet.tokens
        assert len(wallet.tokens) <= 3


def test_screen_verdicts_appear_in_the_report():
    from cabal.report import to_markdown, to_text

    result = analyze(
        [generate_launch().snapshot, generate_dud().snapshot], criteria=ScreenCriteria()
    )
    md = to_markdown(result)
    assert "Pump screen" in md and "skipped" in md
    assert "cleared the screen" in md
    assert "skipped as duds" in to_text(result)


def test_infer_quote_tokens_finds_the_common_side():
    """The asset on one side of most pools is the quote asset."""
    pairs = [(f"0x{i:040x}", WETH, f"0x{i + 100:040x}") for i in range(5)]
    pairs.append(("0x" + "f" * 40, "0x" + "ab" * 20, "0x" + "cd" * 20))
    quotes = infer_quote_tokens(pairs, min_pools=3)
    assert quotes == [WETH]


def test_build_candidates_pairs_each_token_with_its_quote():
    token_a, token_b = "0x" + "a1" * 20, "0x" + "b2" * 20
    pairs = [
        ("0x" + "01" * 20, WETH, token_a),
        ("0x" + "02" * 20, token_a, WETH),  # a second pool for the same token
        ("0x" + "03" * 20, token_b, WETH),
        ("0x" + "04" * 20, WETH, QUOTE),    # quote/quote: not a launch
        ("0x" + "05" * 20, token_a, token_b),  # neither side is a quote: unpriceable
    ]
    candidates = {c.token: c for c in build_candidates(pairs, [WETH, QUOTE])}
    assert set(candidates) == {token_a, token_b}
    assert candidates[token_a].quote == WETH
    assert len(candidates[token_a].pools) == 2


def test_discover_screens_candidates_and_ranks_winners_first():
    """The sweep should price each launch and sort the runners to the top."""
    from cabal.discover import discover_pumped_tokens

    runner, dud = generate_launch(), generate_dud()
    by_token = {l.snapshot.token: l for l in (runner, dud)}

    class StubSource:
        def discover_pools(self, lo, hi, v2, v3):
            return [
                (l.pool, l.snapshot.token, l.quote) for l in (runner, dud)
            ] + [("0x" + "0e" * 20, runner.quote, dud.quote)]

        def token_metadata(self, token):
            return by_token[token].snapshot.symbol, 18

        def transfers(self, token, lo, hi, topics_extra=None):
            return [t for t in by_token[token].snapshot.transfers if t.token == token]

        def quote_legs(self, quotes, pools, lo, hi):
            launch = next(l for l in (runner, dud) if l.quote in quotes)
            return [t for t in launch.snapshot.transfers if t.token in quotes]

    found = discover_pumped_tokens(StubSource(), 0, 10_000, criteria=ScreenCriteria())
    assert [c.token for c in found] == [runner.snapshot.token, dud.snapshot.token]
    assert found[0].verdict.passed and not found[1].verdict.passed
