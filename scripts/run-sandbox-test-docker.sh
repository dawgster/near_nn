#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="${IMAGE_NAME:-near-nn-sandbox-test}"
rust_toolchain="${RUST_TOOLCHAIN:-stable}"

docker build \
  --build-arg "RUST_TOOLCHAIN=${rust_toolchain}" \
  -t "${image_name}" \
  -f "${repo_root}/Dockerfile.sandbox" \
  "${repo_root}"

docker run --rm \
  -e "NEAR_CONTRACT_RUST_TOOLCHAIN=${NEAR_CONTRACT_RUST_TOOLCHAIN:-1.86.0}" \
  -e "NEAR_SANDBOX_TEST_VERSION=${NEAR_SANDBOX_TEST_VERSION:-2.11.0}" \
  -v "${repo_root}:/workspace" \
  -w /workspace \
  "${image_name}" \
  bash -lc '
    set -euo pipefail
    export CARGO_TARGET_DIR=/tmp/near-nn-target
    cargo test --test sandbox -- --nocapture
    cargo test --manifest-path mnist_mlp_contract/Cargo.toml --test sandbox -- --nocapture
    cargo test --manifest-path hotdog_cnn_contract/Cargo.toml --test sandbox -- --nocapture
    cargo test --manifest-path flappy_bird_contract/Cargo.toml --test sandbox -- --nocapture
  '
