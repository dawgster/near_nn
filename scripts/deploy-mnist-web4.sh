#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/deploy-mnist-web4.sh <contract-account-id> [testnet|mainnet]

Examples:
  scripts/deploy-mnist-web4.sh my-mnist-demo.testnet
  SIGNER_ACCOUNT_ID=my-mnist-demo.testnet scripts/deploy-mnist-web4.sh my-mnist-demo.testnet testnet

Environment variables:
  SIGNER_ACCOUNT_ID   Signer for the init transaction. Defaults to CONTRACT_ID.
  RUST_TOOLCHAIN      Rust toolchain for contract build. Defaults to 1.86.0.
  PREPAID_GAS         Gas for init call. Defaults to "100 Tgas".
  SKIP_INIT           Set to 1 to skip the `new` init call.
  RUN_SMOKE_TEST      Set to 0 to skip the final model_info view call.
EOF
}

if [[ "${1:-}" == "" ]] || [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 2 ]]; then
  usage
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
contract_dir="${repo_root}/mnist_mlp_contract"

contract_id="$1"
network="${2:-testnet}"
signer_account_id="${SIGNER_ACCOUNT_ID:-$contract_id}"
rust_toolchain="${RUST_TOOLCHAIN:-1.86.0}"
prepaid_gas="${PREPAID_GAS:-100 Tgas}"
skip_init="${SKIP_INIT:-0}"
run_smoke_test="${RUN_SMOKE_TEST:-1}"
build_target_dir="${contract_dir}/target/deploy-build"
wasm_path="${build_target_dir}/near/near_mnist_mlp_demo.wasm"

if [[ "$network" != "testnet" && "$network" != "mainnet" ]]; then
  echo "Unsupported network: $network" >&2
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo is required" >&2
  exit 1
fi

if ! command -v rustup >/dev/null 2>&1; then
  echo "rustup is required" >&2
  exit 1
fi

if ! command -v near >/dev/null 2>&1; then
  echo "near-cli-rs is required" >&2
  exit 1
fi

if ! cargo near --version >/dev/null 2>&1; then
  echo "cargo-near is required. Install it first." >&2
  echo "Installer: https://github.com/near/cargo-near" >&2
  exit 1
fi

echo "Ensuring Rust toolchain ${rust_toolchain} with wasm target is installed..."
rustup toolchain install "${rust_toolchain}" --profile minimal >/dev/null
rustup target add wasm32-unknown-unknown --toolchain "${rust_toolchain}" >/dev/null

echo "Building MNIST Web4 contract for ${contract_id} on ${network}..."
(
  cd "${contract_dir}"
  CARGO_TARGET_DIR="${build_target_dir}" \
    cargo +"${rust_toolchain}" near build non-reproducible-wasm --no-abi
)

if [[ ! -f "${wasm_path}" ]]; then
  echo "Expected wasm artifact was not produced: ${wasm_path}" >&2
  exit 1
fi

echo "Deploying ${wasm_path} to ${contract_id}..."
near contract deploy "${contract_id}" \
  use-file "${wasm_path}" \
  without-init-call \
  network-config "${network}" \
  sign-with-keychain \
  send

if [[ "${skip_init}" != "1" ]]; then
  echo "Initializing contract with new() using signer ${signer_account_id}..."
  near contract call-function as-transaction "${contract_id}" new json-args '{}' \
    prepaid-gas "${prepaid_gas}" \
    attached-deposit '0 NEAR' \
    sign-as "${signer_account_id}" \
    network-config "${network}" \
    sign-with-keychain \
    send
fi

if [[ "${run_smoke_test}" != "0" ]]; then
  echo "Running smoke test: model_info"
  near contract call-function as-read-only "${contract_id}" model_info json-args '{}' \
    network-config "${network}" \
    now
fi

page_url="https://${contract_id}.page"

echo
echo "Deployment complete."
echo "Web4 URL: ${page_url}"
echo "Contract ID: ${contract_id}"
