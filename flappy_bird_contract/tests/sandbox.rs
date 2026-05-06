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
struct GameConfig {
    canvas_width: i32,
    canvas_height: i32,
    scale: i32,
    pipe_gap: i32,
}

#[derive(Debug, Deserialize)]
struct GameState {
    frame: u16,
    score: u16,
    alive: bool,
}

#[derive(Debug, Deserialize)]
struct SimulationResult {
    final_state: GameState,
    frames_simulated: u16,
    normalized_flap_frames: Vec<u16>,
}

#[derive(Debug, Deserialize)]
struct ScoreEntry {
    account_id: String,
    score: u16,
    frames_survived: u16,
}

#[tokio::test]
async fn runs_flappy_bird_in_near_sandbox() -> Result<()> {
    let wasm = build_contract_wasm()?;
    let sandbox_version =
        std::env::var("NEAR_SANDBOX_TEST_VERSION").unwrap_or_else(|_| "2.11.0".to_string());
    let sandbox = Sandbox::start_sandbox_with_version(&sandbox_version).await?;
    let network = NetworkConfig::from_rpc_url("sandbox", sandbox.rpc_addr.parse()?);
    let contract_id = config::DEFAULT_GENESIS_ACCOUNT.to_owned();
    let signer = root_signer()?;

    deploy_contract(&network, &contract_id, signer.clone(), wasm).await?;
    init_contract(&network, &contract_id, signer.clone()).await?;

    let info: Data<GameConfig> = Contract(contract_id.clone())
        .call_function("game_config", ())
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(info.data.canvas_width, 288);
    assert_eq!(info.data.canvas_height, 512);
    assert_eq!(info.data.scale, 1_000);
    assert_eq!(info.data.pipe_gap, 132);

    let no_flap: Data<SimulationResult> = Contract(contract_id.clone())
        .call_function("simulate", json!({ "flap_frames": [], "frames": null }))
        .read_only()
        .fetch_from(&network)
        .await?;
    assert!(!no_flap.data.final_state.alive);
    assert_eq!(no_flap.data.final_state.score, 0);

    let flaps = (10u16..1_200u16).step_by(31).collect::<Vec<_>>();
    let scoring_replay: Data<SimulationResult> = Contract(contract_id.clone())
        .call_function(
            "simulate",
            json!({ "flap_frames": flaps.clone(), "frames": null }),
        )
        .read_only()
        .fetch_from(&network)
        .await?;
    assert!(scoring_replay.data.final_state.score > 0);
    assert_eq!(scoring_replay.data.normalized_flap_frames, flaps);

    let tx_result = Contract(contract_id.clone())
        .call_function(
            "submit_score",
            json!({ "flap_frames": flaps, "display_name": "sandbox" }),
        )
        .transaction()
        .with_signer(contract_id.clone(), signer.clone())
        .send_to(&network)
        .await?
        .into_full()
        .expect("submit_score transaction should wait for a full execution result");
    let tx_gas_burnt = tx_result.total_gas_burnt;
    let submitted: SimulationResult = tx_result.json()?;
    assert_eq!(
        submitted.final_state.score,
        scoring_replay.data.final_state.score
    );
    assert_eq!(
        submitted.final_state.frame,
        scoring_replay.data.final_state.frame
    );
    println!(
        "submit_score transaction gas: {} gas ({:.3} Tgas)",
        tx_gas_burnt.as_gas(),
        tx_gas_burnt.as_gas() as f64 / 1_000_000_000_000.0
    );

    let leaderboard: Data<Vec<ScoreEntry>> = Contract(contract_id.clone())
        .call_function("leaderboard", ())
        .read_only()
        .fetch_from(&network)
        .await?;
    assert_eq!(leaderboard.data.len(), 1);
    assert_eq!(leaderboard.data[0].account_id, contract_id.to_string());
    assert_eq!(
        leaderboard.data[0].score,
        scoring_replay.data.final_state.score
    );
    assert_eq!(
        leaderboard.data[0].frames_survived,
        scoring_replay.data.frames_simulated
    );

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
            .join("near_flappy_bird_demo")
            .join("near_flappy_bird_demo.wasm"),
        near_target_dir.join("near_flappy_bird_demo.wasm"),
        target_dir
            .join("wasm32-unknown-unknown")
            .join("release")
            .join("near_flappy_bird_demo.wasm"),
    ];

    candidates
        .into_iter()
        .find(|path| path.exists())
        .unwrap_or_else(|| {
            near_target_dir
                .join("near_flappy_bird_demo")
                .join("near_flappy_bird_demo.wasm")
        })
}

fn sandbox_target_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join("sandbox-build")
}
