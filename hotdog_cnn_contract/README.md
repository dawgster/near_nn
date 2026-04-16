# Hotdog CNN Contract

This crate is a second image-classification demo for NEAR. It runs a tiny quantized RGB CNN for `hotdog` vs `not_hotdog` inference completely on-chain.

- Input: `64x64x3` RGB pixels in the `0..255` range
- Architecture: `3x3 conv stride 2 -> pool -> 3x3 conv -> pool -> 3x3 conv -> global average pool -> linear`
- Output: `2` logits for `hotdog` and `not_hotdog`
- Quantization: integer weights with per-layer scales

The model is trained offline, then exported into `src/model_data.rs`. The exporter accepts either:
- the small `truepositive/hotdog_nothotdog` layout: `train/` + `val/`
- the larger Kaggle-style layout: `train/` + `test/`

## Build

```bash
cargo build --manifest-path hotdog_cnn_contract/Cargo.toml --target wasm32-unknown-unknown --release
```

## Test

```bash
cargo test --manifest-path hotdog_cnn_contract/Cargo.toml
CARGO_TARGET_DIR=/tmp/near-nn-target cargo test --manifest-path hotdog_cnn_contract/Cargo.toml --test sandbox -- --nocapture
```

## Regenerate The Embedded Model

Clone or extract the dataset locally once.

Small Hugging Face / GitHub copy:

```bash
git clone https://github.com/truepositive/hotdog_nothotdog /tmp/hotdog_nothotdog
```

Larger Kaggle export:

```bash
unzip hot-dog-not-hot-dog.zip -d /tmp/hotdog_kaggle
```

Then retrain and export:

```bash
HOTDOG_DATASET_DIR=/tmp/hotdog_kaggle hotdog_cnn_contract/.venv/bin/python hotdog_cnn_contract/scripts/export_model.py
```

Useful overrides while iterating:

```bash
HOTDOG_TRAINING_SEEDS=7,11,19 HOTDOG_EPOCHS=20 HOTDOG_MODEL_DATA_OUT=/tmp/hotdog_model_data.rs hotdog_cnn_contract/.venv/bin/python hotdog_cnn_contract/scripts/export_model.py
```

## Contract methods

- `new()`
- `model_info()`
- `predict_pixels({ "pixels": [...] })`
- `predict_sample({ "sample_index": 0 })`
- `sample_pixels({ "sample_index": 0 })`
- `sample_predictions()`

`predict_pixels` expects exactly `12288` integers in `0..255`, flattened row-major in HWC order for a `64x64` RGB image.
