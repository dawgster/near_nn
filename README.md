# NEAR Neural Network Demo

This project is a minimal NEAR smart contract written in Rust that compiles to WebAssembly and runs a tiny two-layer neural network on-chain.

The root crate is the XOR example. Separate image demos live in [mnist_mlp_contract](/home/kuba/Repositories/near_nn/mnist_mlp_contract/README.md:1) and [hotdog_cnn_contract](/home/kuba/Repositories/near_nn/hotdog_cnn_contract/README.md:1).

The network is a fixed-point MLP wired to solve XOR:

- Input layer: 2 neurons
- Hidden layer: 2 neurons with ReLU
- Output layer: 1 neuron
- Numeric format: integers scaled by `1000`

Using scaled integers keeps the demo deterministic and cheap to execute inside a blockchain contract while still showing matrix multiplication and activation logic in WASM.

## Contract methods

- `new_xor_demo()`: initializes the model weights and biases
- `model_info()`: returns the network dimensions and scale
- `predict({ "inputs": [x1, x2] })`: runs inference
- `xor_truth_table()`: returns the four binary XOR predictions

## Build locally

Install the WASM target once:

```bash
rustup target add wasm32-unknown-unknown
```

Build with plain Cargo:

```bash
cargo build --target wasm32-unknown-unknown --release
```

The contract WASM will be at:

```bash
target/wasm32-unknown-unknown/release/near_nn_demo.wasm
```

If you use `cargo-near`, current NEAR docs also support:

```bash
cargo near build
```

## Test locally

```bash
cargo test
```

Run the end-to-end sandbox integration tests:

```bash
cargo test --test sandbox -- --nocapture
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path mnist_mlp_contract/Cargo.toml --test sandbox -- --nocapture
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path hotdog_cnn_contract/Cargo.toml --test sandbox -- --nocapture
```

On older Linux hosts, the downloaded `near-sandbox` binary may fail to start because of a libc mismatch. The repo includes a Docker wrapper that runs both sandbox suites in Ubuntu 24.04 instead:

```bash
bash ./scripts/run-sandbox-test-docker.sh
```

Or manually:

```bash
docker build -t near-nn-sandbox-test -f Dockerfile.sandbox .
docker run --rm -v "$(pwd):/workspace" -w /workspace near-nn-sandbox-test bash -lc 'export CARGO_TARGET_DIR=/tmp/near-nn-target && cargo test --test sandbox -- --nocapture && cargo test --manifest-path mnist_mlp_contract/Cargo.toml --test sandbox -- --nocapture && cargo test --manifest-path hotdog_cnn_contract/Cargo.toml --test sandbox -- --nocapture'
```

## Deploy to NEAR testnet

The current NEAR docs describe deployment with `near deploy <accountId> <path-to-wasm>`.

Example flow:

```bash
near create-account <your-contract>.testnet --useFaucet
near deploy <your-contract>.testnet ./target/wasm32-unknown-unknown/release/near_nn_demo.wasm
near call <your-contract>.testnet new_xor_demo '{}' --useAccount <your-contract>.testnet
```

## Call the model

Run XOR inference for `(1, 0)`:

```bash
near view <your-contract>.testnet predict '{"inputs":[1000,0]}'
```

Fetch the full truth table:

```bash
near view <your-contract>.testnet xor_truth_table '{}'
```

Expected classification behavior:

- `[0, 0] -> false`
- `[1000, 0] -> true`
- `[0, 1000] -> true`
- `[1000, 1000] -> false`
