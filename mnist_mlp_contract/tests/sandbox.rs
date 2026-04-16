use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;

use anyhow::{Context, Result};
use near_api::{Contract, Data, NetworkConfig, Signer};
use near_sandbox::{config, Sandbox};
use serde::Deserialize;
use serde_json::json;

#[derive(Debug, Deserialize)]
struct ModelInfo {
    input_size: usize,
    hidden_size: usize,
    output_size: usize,
    input_scale: i32,
    weight_scale: i32,
}

#[derive(Debug, Deserialize)]
struct DigitPrediction {
    predicted_digit: u8,
}

#[derive(Debug, Deserialize)]
struct SamplePrediction {
    sample_digit: u8,
    predicted_digit: u8,
}

#[tokio::test]
async fn runs_mnist_model_in_near_sandbox() -> Result<()> {
    let wasm = build_contract_wasm()?;
    let sandbox_version =
        std::env::var("NEAR_SANDBOX_TEST_VERSION").unwrap_or_else(|_| "2.11.0".to_string());
    let sandbox = Sandbox::start_sandbox_with_version(&sandbox_version).await?;
    let network = NetworkConfig::from_rpc_url("sandbox", sandbox.rpc_addr.parse()?);
    let contract_id = config::DEFAULT_GENESIS_ACCOUNT.to_owned();
    let signer = root_signer()?;

    deploy_contract(&network, &contract_id, signer.clone(), wasm).await?;
    init_contract(&network, &contract_id, signer.clone()).await?;

    let info: Data<ModelInfo> = Contract(contract_id.clone())
        .call_function("model_info", ())
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(info.data.input_size, 784);
    assert_eq!(info.data.hidden_size, 24);
    assert_eq!(info.data.output_size, 10);
    assert_eq!(info.data.input_scale, 255);
    assert_eq!(info.data.weight_scale, 256);

    let prediction: Data<DigitPrediction> = Contract(contract_id.clone())
        .call_function("predict_sample", json!({ "digit": 7 }))
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(prediction.data.predicted_digit, 7);

    let uploaded_pixels: Data<Vec<u8>> = Contract(contract_id.clone())
        .call_function("sample_pixels", json!({ "digit": 7 }))
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(uploaded_pixels.data.len(), 784);

    let uploaded_prediction: Data<DigitPrediction> = Contract(contract_id.clone())
        .call_function("predict_pixels", json!({ "pixels": uploaded_pixels.data }))
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(uploaded_prediction.data.predicted_digit, 7);

    let uploaded_pixels: Data<Vec<u8>> = Contract(contract_id.clone())
        .call_function("sample_pixels", json!({ "digit": 7 }))
        .read_only()
        .fetch_from(&network)
        .await?;
    let tx_result = Contract(contract_id.clone())
        .call_function("predict_pixels", json!({ "pixels": uploaded_pixels.data }))
        .transaction()
        .with_signer(contract_id.clone(), signer.clone())
        .send_to(&network)
        .await?
        .into_full()
        .expect("predict_pixels transaction should wait for a full execution result");
    let tx_gas_burnt = tx_result.total_gas_burnt;
    let tx_prediction: DigitPrediction = tx_result.json()?;
    assert_eq!(tx_prediction.predicted_digit, 7);
    println!(
        "predict_pixels transaction gas: {} gas ({:.3} Tgas)",
        tx_gas_burnt.as_gas(),
        tx_gas_burnt.as_gas() as f64 / 1_000_000_000_000.0
    );

    let predictions: Data<Vec<SamplePrediction>> = Contract(contract_id)
        .call_function("sample_predictions", ())
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(predictions.data.len(), 10);
    assert!(predictions
        .data
        .iter()
        .all(|prediction| prediction.sample_digit == prediction.predicted_digit));

    Ok(())
}

async fn deploy_contract(
    network: &NetworkConfig,
    contract_id: &near_api::AccountId,
    signer: Arc<Signer>,
    wasm: Vec<u8>,
) -> Result<()> {
    Contract::deploy(contract_id.clone())
        .use_code(wasm)
        .without_init_call()
        .with_signer(signer)
        .send_to(network)
        .await?
        .assert_success();
    Ok(())
}

async fn init_contract(
    network: &NetworkConfig,
    contract_id: &near_api::AccountId,
    signer: Arc<Signer>,
) -> Result<()> {
    Contract(contract_id.clone())
        .call_function("new", ())
        .transaction()
        .with_signer(contract_id.clone(), signer)
        .send_to(network)
        .await?
        .assert_success();
    Ok(())
}

fn root_signer() -> Result<Arc<Signer>> {
    Signer::from_secret_key(config::DEFAULT_GENESIS_ACCOUNT_PRIVATE_KEY.parse()?)
        .map_err(Into::into)
}

fn build_contract_wasm() -> Result<Vec<u8>> {
    let rust_toolchain =
        std::env::var("NEAR_CONTRACT_RUST_TOOLCHAIN").unwrap_or_else(|_| "1.86.0".to_string());
    ensure_wasm_target(&rust_toolchain)?;

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let status = Command::new("cargo")
        .env("CARGO_TARGET_DIR", sandbox_target_dir())
        .current_dir(&manifest_dir)
        .args([
            &format!("+{rust_toolchain}"),
            "near",
            "build",
            "non-reproducible-wasm",
            "--no-abi",
        ])
        .status()
        .context("failed to invoke cargo near build for wasm artifact")?;

    anyhow::ensure!(
        status.success(),
        "cargo near build failed with status: {status}"
    );

    let wasm_path = wasm_artifact_path();
    fs::read(&wasm_path).with_context(|| format!("failed to read {}", wasm_path.display()))
}

fn ensure_wasm_target(rust_toolchain: &str) -> Result<()> {
    let install_status = Command::new("rustup")
        .args([
            "toolchain",
            "install",
            rust_toolchain,
            "--profile",
            "minimal",
        ])
        .status()
        .with_context(|| format!("failed to install Rust toolchain {rust_toolchain}"))?;

    anyhow::ensure!(
        install_status.success(),
        "rustup toolchain install {rust_toolchain} failed with status: {install_status}"
    );

    let target_status = Command::new("rustup")
        .args([
            "target",
            "add",
            "wasm32-unknown-unknown",
            "--toolchain",
            rust_toolchain,
        ])
        .status()
        .with_context(|| {
            format!("failed to install wasm32-unknown-unknown for toolchain {rust_toolchain}")
        })?;

    anyhow::ensure!(
        target_status.success(),
        "rustup target add wasm32-unknown-unknown --toolchain {rust_toolchain} failed with status: {target_status}"
    );

    Ok(())
}

fn wasm_artifact_path() -> PathBuf {
    let target_dir = sandbox_target_dir();
    let near_target_dir = target_dir.join("near");
    let candidates = [
        near_target_dir
            .join("near_mnist_mlp_demo")
            .join("near_mnist_mlp_demo.wasm"),
        near_target_dir.join("near_mnist_mlp_demo.wasm"),
        target_dir
            .join("wasm32-unknown-unknown")
            .join("release")
            .join("near_mnist_mlp_demo.wasm"),
    ];

    candidates
        .into_iter()
        .find(|path| path.exists())
        .unwrap_or_else(|| {
            near_target_dir
                .join("near_mnist_mlp_demo")
                .join("near_mnist_mlp_demo.wasm")
        })
}

fn sandbox_target_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join("sandbox-build")
}
