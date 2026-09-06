# cabal_detector — insider wallet detection for token launches

Finds the wallets that were **in before everyone else on coins that actually
ran**: the ones holding supply before a pool existed, the ones that bought in the
opening block, and the ones that do it again on the next winner.

Coins that went nowhere are screened out before any wallet is named. Whoever was
early on a token that never moved made nothing, so their addresses are noise.

Built for [Robinhood Chain](https://docs.robinhood.com/chain/connecting) (EVM,
Arbitrum Orbit, chain id **4663**), and works on any EVM chain by pointing
`--rpc-url` somewhere else.

## The two questions this answers

| You asked | The signal |
| --- | --- |
| *"who got allocated before the sale?"* | `pre_liquidity_allocation` — held supply before a pool existed at all. It was handed to them; they never bought it. |
| *"who bought before it pumped?"* | `bought_before_pump` + `snipe_latency` + `early_buyer_rank` — already holding when the run-up started, having entered at or near the first public trade. |
| *"only on coins that actually pumped"* | The pump screen runs before any wallet scoring, so duds never contribute addresses. |

Neither is conclusive alone, which is the whole design: a wallet is ranked by how
many independent signals converge on it, and every flag ships the sentence that
justifies it.

## Quick start

No RPC needed to see what the output looks like — there is a built-in fixture
with planted insiders plus one launch that goes nowhere:

```bash
cd cabal_detector
pip install -r requirements.txt
python -m cabal demo
```

### The full workflow: chain → winners → wallets

```bash
# 1. Sweep a block range for launches, keep only the ones that pumped.
python -m cabal discover \
  --factory-v2 0xDEX_FACTORY \
  --lookback 200000 \
  --min-pump 5 \
  --write-tokens pumped.txt

# 2. Ingest only those. Slow and rate-limited, so it runs on the shortlist.
python -m cabal snapshot --tokens-file pumped.txt --quote 0xWETH --out-dir snapshots

# 3. Score. Fast — re-run freely while tuning.
python -m cabal analyze --snapshot snapshots/*.json --format markdown --out report.md
```

`discover` infers the quote asset from pool composition (the token on one side of
most pools is the quote), so you do not need to know the chain's WETH address up
front. Already have snapshots and just want the triage? `cabal screen --snapshot
snapshots/*.json --write-tokens pumped.txt`.

If you already know the token you care about, skip straight to step 2.

Point it at a different endpoint or chain:

```bash
export CABAL_RPC_URL=https://your-endpoint
python -m cabal snapshot --token 0xTOKEN                 # Robinhood Chain preset
python -m cabal snapshot --chain robinhood-testnet --token 0xTOKEN
```

The strongest results come from analyzing **several pumped launches at once** —
repeat offenders are what separate a cabal from a lucky buyer:

```bash
python -m cabal analyze --snapshot snapshots/*.json --format markdown
```

## The pump screen

A token is analyzed only if it cleared all of these. The report lists every
token considered, passed and skipped, with the multiple it actually reached.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--min-pump` | `3` | Peak price over the launch baseline. The launch baseline is the median of the first few fills, so one odd print cannot set the denominator. |
| `--min-buyers` | `25` | Unique buyers. Stops four trades between two wallets printing a fake 100x. |
| `--min-trades` | `20` | Total trades. |
| `--min-volume` | off | Minimum quote volume in raw units, for filtering thin books. |
| `--include-unpriced` | off | Keep tokens whose price could not be reconstructed (judged on activity alone). |
| `--include-duds` | off | Turn the screen off entirely and analyze everything. |

This also sharpens the tool's strongest signal. Once the universe is "coins that
ran", `cross_token_recidivism` stops meaning *"this wallet buys a lot of tokens"*
and starts meaning *"this wallet is early on winners"* — which is the thing you
actually want to know.

## Signals

| Signal | Default weight | Fires when |
| --- | --- | --- |
| `pre_liquidity_allocation` | 0.35 | Held supply before any pool existed — allocated, not bought. |
| `cross_token_recidivism` | 0.35 | In the early/allocated cohort across 2+ separate launches. |
| `deployer_link` | 0.30 | Received supply from the deployer, was gas-funded by them, or shares their funding source. |
| `pre_public_trade` | 0.25 | Acquired after liquidity was added but before the first public trade. |
| `sell_into_pump` | 0.25 | Distributed most of its position into the run-up it was early to. |
| `snipe_latency` | 0.20 | Bought in the opening block or two. |
| `bought_before_pump` | 0.20 | Already holding when the run-up began, all of it acquired beforehand. |
| `funding_cluster` | 0.20 | Linked to other flagged wallets by shared gas funding. |
| `synchronized_buys` | 0.15 | Entered alongside far more wallets than the launch's own buy rate explains. |
| `early_buyer_rank` | 0.15 | Among the first buyers overall. |
| `fresh_wallet` | 0.10 | First funded shortly before the launch. |

Score is the weighted sum mapped onto 0–100, tiered `likely_cabal` (≥70),
`suspect` (≥45), `watch` (≥25). Across multiple tokens each signal counts at its
**best** observation rather than summing, so one launch cannot inflate a wallet
past a threshold — repetition surfaces through `cross_token_recidivism` instead.

Retune anything without touching code:

```bash
echo '{"score_normalizer": 2.0, "weights": {"fresh_wallet": 0.0}}' > cfg.json
python -m cabal analyze --snapshot snapshots/*.json --config cfg.json
```

## How it works

```
RPC ──► discover ──► screen ──► snapshot ──► timeline ──► features ──► detectors ──► score
        (pools      (did it     (transfers,  (deploy /    (per wallet)  (11 signals)  (+ clusters)
         created)    pump?)      funding)     liquidity /
                        │                     first trade,
                     duds ✗                   pump windows)
```

The screen sits early and deliberately: it needs only transfers, no funding scan
and no deploy-block search, so rejecting a token costs almost nothing.

Three anchors drive everything: **deploy** (first mint), **liquidity** (tokens
first reach a pool — the sale opens), and **first trade** (first pool→wallet buy
— the public could finally participate). Anything acquired before liquidity was
an allocation; anything between liquidity and first trade was a head start.

Some deliberate choices:

- **Trades are derived from ERC-20 `Transfer` logs against pool addresses**, not
  from DEX `Swap` events. That works across Uniswap V2/V3 forks and any other AMM
  with no per-venue decoding, and it resolves router hops so an aggregator does
  not get flagged as the earliest buyer of every token on the chain.
- **Event topics are derived from signature strings** by a bundled pure-Python
  keccak-256, so a typo fails a test instead of silently returning zero logs.
- **Pumps are detected from the trade price series**, and the window extends past
  the peak — insiders distribute on the way down too.
- **Funding clusters exclude hub funders.** An exchange hot wallet funds
  thousands of people; treating that as a shared operator would put every retail
  buyer in one giant "cluster".
- **Native funding is scanned last and only for the early cohort**, because
  value transfers emit no logs and full-block scanning is by far the most
  expensive call path. Use `--no-funding` to skip it entirely.

## Limitations — read before acting on a flag

- **These are heuristics, not proof.** Market makers, launch partners, CEX hot
  wallets, treasury/vesting contracts and ordinary fast bots all legitimately
  trip some of these signals. The tool ranks wallets for review; it does not
  establish intent.
- **Pool identification drives most signals.** Pools are found from configured
  factories, `--pool` flags, and a two-way-flow heuristic that can also match a
  CEX hot wallet. Pass `--pool` explicitly when you know the venue.
- **Pricing needs a quote leg in the same transaction.** Without `--quote` the
  tool prices against whatever counter-asset moved in the same tx, which is right
  for a simple swap and wrong for some multi-hop routes. Pools quoted in *native*
  ETH emit no ERC-20 transfer for the quote side at all, so those tokens come out
  unpriced — the screen skips them unless you pass `--include-unpriced`.
- **The screen judges outcome, not quality.** A coin that pumped on wash trading
  passes; `--min-buyers` and `--min-volume` are the levers against that.
- **Funding-graph signals need an archive-capable endpoint**; the public rate-
  limited RPC will be slow, and `find_deploy_block` needs historical state.
  Without funding data the allocation and timing signals still work.
- **A partial scan weakens allocation signals.** If `--from-block` starts after
  deployment there is no mint to anchor supply, and the report warns about it.
- **One wallet ≠ one person, and one person ≠ one wallet.** Clustering catches
  shared funding, not shared intent.
- **Not built for Solana-style launchpads.** The ingestion layer is EVM
  `eth_getLogs`; the detectors themselves only need transfers, trades and funding
  edges, so a non-EVM adapter that emits `TokenSnapshot` would reuse all of the
  scoring.

## Tests

```bash
cd cabal_detector && python -m pytest -q
```

69 tests. The end-to-end ones run against a synthetic launch with planted
insiders, snipers and retail, and assert both directions: every planted wallet is
flagged, and no innocent wallet is. A second fixture is a launch with the same
insider structure that simply never runs — its wallets must never be named.

## Layout

```
cabal/
  keccak.py      pure-python keccak-256; topics derived, not pasted
  abi.py         log decoding and function selectors
  chains.py      chain presets (Robinhood mainnet 4663 / testnet 46630)
  models.py      Transfer / FundingEdge / Trade / snapshot / report types
  sources/       JSON-RPC ingestion, snapshot persistence
  ingest.py      RPC orchestration -> TokenSnapshot
  screen.py      the pump test: is this coin worth analyzing at all?
  discover.py    sweep a block range for launches, keep the winners
  timeline.py    launch anchors, trade reconstruction, pump detection
  features.py    per-wallet feature extraction
  detectors.py   the 11 signals
  clustering.py  funding-graph union-find
  analysis.py    scoring and cross-token aggregation
  report.py      text / markdown / CSV / JSON output
  cli.py         discover | screen | snapshot | analyze | demo
  synthetic.py   ground-truth fixture
```
