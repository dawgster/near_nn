# near_nn — Neural Networks on NEAR

Three Rust smart contracts that run neural network inference **entirely on-chain**, one deterministic on-chain arcade game, plus a Cloudflare Worker that serves the frontends through custom domains.

No oracles, no off-chain compute, no trusted relayers — the weights live in the contract state, the math runs in WASM inside the NEAR runtime, and anyone with an RPC call can verify the result.

| Contract | Task | Architecture | Input |
| --- | --- | --- | --- |
| [`src/`](src/lib.rs) | XOR | 2 → 2 → 1 MLP, ReLU | 2 scaled ints |
| [`mnist_mlp_contract/`](mnist_mlp_contract/) | Handwritten digits | 784 → 24 → 10 MLP, ReLU | 28×28 grayscale |
| [`hotdog_cnn_contract/`](hotdog_cnn_contract/) | Hotdog / not-hotdog | 3-layer CNN + GAP + linear | 64×64 RGB |
| [`flappy_bird_contract/`](flappy_bird_contract/) | Flappy Bird | Fixed-point replay verifier + leaderboard | Flap frame list |

The neural-network contracts use **integer quantization** with per-layer scales so inference is deterministic and cheap inside the WASM sandbox. The Flappy Bird contract uses the same deterministic integer style for physics, pipe generation, replay verification, and scoring.

## Live demos

- MNIST digit classifier — <https://icypee.xyz>
- Hotdog / not-hotdog — <https://hotdog.icypee.xyz>

Both frontends are served from NEAR contracts via [Web4](https://web4.near.page), with a Cloudflare Worker proxying the contract's `web4_get` response to a custom domain.

## Repo layout

```
.
├── src/                       # XOR MLP (root crate)
├── mnist_mlp_contract/        # MNIST MLP + Web4 frontend
├── hotdog_cnn_contract/       # Hotdog CNN + Web4 frontend
├── flappy_bird_contract/      # Fixed-point Flappy Bird + Web4 frontend
├── cloudflare-worker/         # Web4 proxy for custom domains
├── scripts/                   # Deploy + sandbox helpers
└── Dockerfile.sandbox         # Ubuntu 24.04 runner for near-sandbox tests
```

## Quick start

Install the WASM target once:

```bash
rustup target add wasm32-unknown-unknown
```

Build every contract:

```bash
cargo build --target wasm32-unknown-unknown --release
cargo build --manifest-path mnist_mlp_contract/Cargo.toml --target wasm32-unknown-unknown --release
cargo build --manifest-path hotdog_cnn_contract/Cargo.toml --target wasm32-unknown-unknown --release
cargo build --manifest-path flappy_bird_contract/Cargo.toml --target wasm32-unknown-unknown --release
```

Run the end-to-end sandbox tests (spins up a real `near-sandbox`, deploys each contract, calls inference):

```bash
cargo test --test sandbox -- --nocapture
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path mnist_mlp_contract/Cargo.toml --test sandbox -- --nocapture
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path hotdog_cnn_contract/Cargo.toml --test sandbox -- --nocapture
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path flappy_bird_contract/Cargo.toml --test sandbox -- --nocapture
```

If the sandbox binary fails to start on an older host (libc mismatch), run everything inside Docker instead:

```bash
bash ./scripts/run-sandbox-test-docker.sh
```

## How it works

Each contract ships its trained weights as quantized integers in a generated `model_data.rs`. At inference time the contract:

1. Reads input pixels (or scaled floats).
2. Runs matmul / conv / ReLU / pool in plain `i32` arithmetic.
3. Rescales by the stored per-layer scale factors.
4. Returns logits (and an argmax class) as JSON.

Training happens offline in Python — see each contract's `scripts/export_model.py`. The output is a Rust source file with the quantized weights that gets re-embedded into the contract WASM on the next build.

## Deploying a contract

Create a testnet account, then use the provided deploy scripts:

```bash
near create-account my-demo.testnet --useFaucet

./scripts/deploy-mnist-web4.sh my-demo.testnet
./scripts/deploy-hotdog-web4.sh my-demo.testnet
./scripts/deploy-flappy-web4.sh my-demo.testnet
```

Each script builds the WASM, deploys it, calls `new()`, runs a smoke test, and prints the Web4 URL (`https://<account>.testnet.page`).

To map a custom domain, edit `cloudflare-worker/wrangler*.jsonc` and deploy the worker:

```bash
./scripts/deploy-cloudflare-worker.sh
```

## Per-contract details

- **XOR** — see top of this README and [`src/lib.rs`](src/lib.rs). Smallest possible end-to-end example.
- **MNIST MLP** — see [`mnist_mlp_contract/README.md`](mnist_mlp_contract/README.md). Includes a Web4 canvas for drawing digits in the browser.
- **Hotdog CNN** — see [`hotdog_cnn_contract/README.md`](hotdog_cnn_contract/README.md). Accepts uploaded images resized to 64×64 RGB.
- **Flappy Bird** — see [`flappy_bird_contract/README.md`](flappy_bird_contract/README.md). Plays locally in the Web4 page and verifies replayed flap frames on-chain.
- **Cloudflare Worker** — see [`cloudflare-worker/README.md`](cloudflare-worker/README.md).

## Calling the XOR contract

```bash
near view my-demo.testnet predict '{"inputs":[1000,0]}'
near view my-demo.testnet xor_truth_table '{}'
```

Expected behavior:

| Input | Output |
| --- | --- |
| `[0, 0]` | `false` |
| `[1000, 0]` | `true` |
| `[0, 1000]` | `true` |
| `[1000, 1000]` | `false` |

## License

MIT — do whatever, but don't blame me if your on-chain model mistakes a dachshund for a hotdog.
