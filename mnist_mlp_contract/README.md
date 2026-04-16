# MNIST MLP Contract

This contract is a separate NEAR demo from the root XOR example. It runs inference for a quantized two-layer MLP trained offline on MNIST.

- Input: `784` grayscale pixels in the `0..255` range
- Hidden layer: `24` neurons with ReLU
- Output: `10` digit logits
- Quantization: integer weights with scale `256`

## Build

```bash
cargo build --manifest-path mnist_mlp_contract/Cargo.toml --target wasm32-unknown-unknown --release
```

WASM output:

```bash
mnist_mlp_contract/target/wasm32-unknown-unknown/release/near_mnist_mlp_demo.wasm
```

## Test

```bash
cargo test --manifest-path mnist_mlp_contract/Cargo.toml
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path mnist_mlp_contract/Cargo.toml --test sandbox -- --nocapture
```

## Deploy

The repo includes a deploy script for the Web4-enabled MNIST contract:

```bash
./scripts/deploy-mnist-web4.sh <account>.testnet
```

Example:

```bash
./scripts/deploy-mnist-web4.sh mnist-demo.testnet
```

The script will:

- build the contract with the NEAR-compatible Rust toolchain
- deploy the wasm to the target account
- call `new()`
- run a `model_info` smoke test
- print the final Web4 URL

## Regenerate The Embedded Model

The contract stores precomputed quantized weights in `src/model_data.rs`. To retrain and regenerate them:

```bash
python3 mnist_mlp_contract/scripts/export_model.py
```

## Contract methods

- `new()`
- `model_info()`
- `predict_pixels({ "pixels": [...] })`
- `predict_sample({ "digit": 7 })`
- `sample_pixels({ "digit": 7 })`
- `sample_predictions()`
- `web4_get({ "path": "/" })`

`predict_pixels` is the custom-upload entrypoint. It expects exactly `784` grayscale values in the `0..255` range, flattened row-major from a `28x28` image.

Example payload:

```json
{
  "pixels": [0, 0, 12, 255, 84]
}
```

The array must contain all `784` pixel values. `sample_pixels` is a convenience method for the demo UI and tests so you can inspect the expected format using one of the embedded samples before sending your own image.

## Web4 Frontend

The contract also serves a single-page Web4 frontend through `web4_get`. After deployment, the same contract can be opened at:

- `https://<account>.testnet.page` on testnet
- `https://<account>.near.page` on mainnet

The page includes:

- a `28x28` drawing pad for custom samples
- buttons for loading the embedded demo digits
- on-chain inference via `predict_pixels`
- logits and predicted digit display

Deploy the contract as usual, initialize it with `new`, then open the `.page` URL for the account.
