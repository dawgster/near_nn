# Flappy Bird Contract

This crate is a deterministic Flappy Bird-style NEAR demo. It follows the same shape as the neural-network contracts in this repo: inputs are passed to a contract method, the WASM contract runs all scoring logic with integer arithmetic, and the Web4 page calls the contract to verify the result.

- Input: sorted or unsorted flap frame numbers
- Simulation: fixed-point gravity, velocity, pipe scrolling, deterministic pipe gaps
- Output: final bird state, collision reason, score, and visible pipes
- State: top 10 replay-verified leaderboard entries

## Build

```bash
cargo build --manifest-path flappy_bird_contract/Cargo.toml --target wasm32-unknown-unknown --release
```

## Test

```bash
cargo test --manifest-path flappy_bird_contract/Cargo.toml
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path flappy_bird_contract/Cargo.toml --test sandbox -- --nocapture
```

## Deploy

```bash
./scripts/deploy-flappy-web4.sh <account>.testnet
```

The script builds the Web4 contract, deploys it, calls `new()`, runs a `game_config` smoke test, and prints the Web4 URL.

## Contract Methods

- `new()`
- `game_config()`
- `simulate({ "flap_frames": [10, 41, 72], "frames": null })`
- `pipe_at({ "index": 0, "frame": 120 })`
- `visible_pipes({ "frame": 120, "count": 4 })`
- `leaderboard()`
- `submit_score({ "flap_frames": [10, 41, 72], "display_name": "player" })`
- `web4_get({ "path": "/" })`

`simulate` accepts `frames: null` to replay until collision or the max frame limit. Supplying a concrete frame count verifies an in-progress browser run against the exact on-chain state at that frame.

## Web4 Frontend

The contract serves the game directly from `web4_get`. There is no separate bundler in this first version: the Rust contract embeds one self-contained HTML document with inline CSS and JavaScript, and Web4 returns it from `/` or `/index.html`.

The page plays locally at 60 FPS, records flap frame numbers, and periodically calls `simulate` over NEAR JSON-RPC to compare the browser state with the contract replay. The `submit_score` method is available for wallet or CLI transactions when you want to persist a verified replay to the leaderboard.

The wallet connector is vendored into the contract as `/near-connect.mjs` from `@hot-labs/near-connect` 0.11.2, so the page, game code, sprites, and connector bootstrap all come from Web4. Wallet executors and wallet approval pages still load from the selected wallet provider.
