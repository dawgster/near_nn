use std::collections::HashMap;

use near_sdk::borsh::{BorshDeserialize, BorshSerialize};
use near_sdk::env;
use near_sdk::json_types::Base64VecU8;
use near_sdk::serde::{Deserialize, Serialize};
use near_sdk::{near, PanicOnDefault};

const SCALE: i32 = 1_000;
const CANVAS_WIDTH: i32 = 288;
const CANVAS_HEIGHT: i32 = 512;
const SKY_HEIGHT: i32 = 448;
const BIRD_X: i32 = 70;
const BIRD_RADIUS: i32 = 12;
const INITIAL_BIRD_Y: i32 = 222 * SCALE;
const INITIAL_VELOCITY: i32 = 0;
const FLAP_VELOCITY: i32 = -7_200;
const GRAVITY: i32 = 430;
const MAX_FALL_VELOCITY: i32 = 9_000;
const PIPE_WIDTH: i32 = 52;
const PIPE_GAP: i32 = 132;
const PIPE_SPACING: i32 = 150;
const PIPE_START_X: i32 = 356;
const PIPE_SCROLL_SPEED: i32 = 2;
const PIPE_MARGIN: i32 = 54;
const MAX_FRAMES: u16 = 3_600;
const MAX_FLAPS: usize = 900;
const LEADERBOARD_LIMIT: usize = 10;
const NEAR_CONNECT_BUNDLE: &str = include_str!("../assets/near-connect-0.11.2.bundle.mjs");
const IRONCLAW_SPRITE: &[u8] = include_bytes!("../assets/ironclaw-sprite.png");

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct GameConfig {
    pub scale: i32,
    pub canvas_width: i32,
    pub canvas_height: i32,
    pub sky_height: i32,
    pub bird_x: i32,
    pub bird_radius: i32,
    pub initial_bird_y: i32,
    pub flap_velocity: i32,
    pub gravity: i32,
    pub max_fall_velocity: i32,
    pub pipe_width: i32,
    pub pipe_gap: i32,
    pub pipe_spacing: i32,
    pub pipe_start_x: i32,
    pub pipe_scroll_speed: i32,
    pub max_frames: u16,
    pub max_flaps: usize,
    pub description: String,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(crate = "near_sdk::serde")]
pub struct Pipe {
    pub index: u16,
    pub x: i32,
    pub gap_center_y: i32,
    pub gap_top: i32,
    pub gap_bottom: i32,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(crate = "near_sdk::serde")]
pub struct GameState {
    pub frame: u16,
    pub bird_y: i32,
    pub velocity: i32,
    pub score: u16,
    pub next_pipe_index: u16,
    pub alive: bool,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct SimulationResult {
    pub final_state: GameState,
    pub frames_simulated: u16,
    pub collision: Option<String>,
    pub visible_pipes: Vec<Pipe>,
    pub normalized_flap_frames: Vec<u16>,
}

#[derive(BorshDeserialize, BorshSerialize, Serialize, Deserialize, Clone)]
#[serde(crate = "near_sdk::serde")]
pub struct ScoreEntry {
    pub account_id: String,
    pub display_name: String,
    pub score: u16,
    pub frames_survived: u16,
    pub flap_count: u16,
    pub submitted_at_ms: u64,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct Web4Request {
    #[serde(rename = "accountId")]
    pub account_id: Option<String>,
    pub path: String,
    pub params: Option<HashMap<String, String>>,
    pub query: Option<HashMap<String, Vec<String>>>,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde", untagged)]
pub enum Web4Response {
    Body {
        #[serde(rename = "contentType")]
        content_type: String,
        body: Base64VecU8,
    },
    Status {
        status: u32,
    },
}

impl Web4Response {
    fn html_response(html: String) -> Self {
        Self::Body {
            content_type: "text/html; charset=UTF-8".to_string(),
            body: html.into_bytes().into(),
        }
    }

    fn javascript_response(script: &'static str) -> Self {
        Self::Body {
            content_type: "text/javascript; charset=UTF-8".to_string(),
            body: script.as_bytes().to_vec().into(),
        }
    }

    fn png_response(image: &'static [u8]) -> Self {
        Self::Body {
            content_type: "image/png".to_string(),
            body: image.to_vec().into(),
        }
    }

    fn status(status: u32) -> Self {
        Self::Status { status }
    }
}

#[derive(PanicOnDefault)]
#[near(contract_state)]
pub struct FlappyBirdContract {
    initialized: bool,
    leaderboard: Vec<ScoreEntry>,
}

#[near]
impl FlappyBirdContract {
    #[init]
    pub fn new() -> Self {
        Self {
            initialized: true,
            leaderboard: Vec::new(),
        }
    }

    pub fn game_config(&self) -> GameConfig {
        GameConfig {
            scale: SCALE,
            canvas_width: CANVAS_WIDTH,
            canvas_height: CANVAS_HEIGHT,
            sky_height: SKY_HEIGHT,
            bird_x: BIRD_X,
            bird_radius: BIRD_RADIUS,
            initial_bird_y: INITIAL_BIRD_Y,
            flap_velocity: FLAP_VELOCITY,
            gravity: GRAVITY,
            max_fall_velocity: MAX_FALL_VELOCITY,
            pipe_width: PIPE_WIDTH,
            pipe_gap: PIPE_GAP,
            pipe_spacing: PIPE_SPACING,
            pipe_start_x: PIPE_START_X,
            pipe_scroll_speed: PIPE_SCROLL_SPEED,
            max_frames: MAX_FRAMES,
            max_flaps: MAX_FLAPS,
            description: "Deterministic fixed-point Flappy Bird clone on NEAR. The contract replays flap frames, advances pipe physics in WASM, detects collisions, and returns a verifiable score.".to_string(),
        }
    }

    pub fn simulate(&self, flap_frames: Vec<u16>, frames: Option<u16>) -> SimulationResult {
        simulate_replay(&flap_frames, frames)
    }

    pub fn pipe_at(&self, index: u16, frame: u16) -> Pipe {
        build_pipe_at(index, frame)
    }

    pub fn visible_pipes(&self, frame: u16, count: Option<u8>) -> Vec<Pipe> {
        collect_visible_pipes(frame.min(MAX_FRAMES), count.unwrap_or(4).min(8) as usize)
    }

    pub fn leaderboard(&self) -> Vec<ScoreEntry> {
        self.leaderboard.clone()
    }

    pub fn submit_score(
        &mut self,
        flap_frames: Vec<u16>,
        display_name: Option<String>,
    ) -> SimulationResult {
        let result = simulate_replay(&flap_frames, None);
        assert!(
            result.collision.is_some() || result.frames_simulated == MAX_FRAMES,
            "score replay must end in a collision or reach max frames"
        );

        let predecessor = env::predecessor_account_id().to_string();
        let entry = ScoreEntry {
            account_id: predecessor.clone(),
            display_name: sanitize_display_name(display_name.unwrap_or(predecessor)),
            score: result.final_state.score,
            frames_survived: result.frames_simulated,
            flap_count: result.normalized_flap_frames.len() as u16,
            submitted_at_ms: env::block_timestamp_ms(),
        };

        self.leaderboard.push(entry);
        self.leaderboard.sort_by(|left, right| {
            right
                .score
                .cmp(&left.score)
                .then_with(|| right.frames_survived.cmp(&left.frames_survived))
                .then_with(|| left.flap_count.cmp(&right.flap_count))
                .then_with(|| left.submitted_at_ms.cmp(&right.submitted_at_ms))
        });
        self.leaderboard.truncate(LEADERBOARD_LIMIT);

        result
    }

    pub fn web4_get(&self, request: Web4Request) -> Web4Response {
        match request.path.as_str() {
            "/" | "/index.html" => {
                Web4Response::html_response(render_web4_page(env::current_account_id().as_str()))
            }
            "/near-connect.mjs" => Web4Response::javascript_response(NEAR_CONNECT_BUNDLE),
            "/ironclaw-sprite.png" => Web4Response::png_response(IRONCLAW_SPRITE),
            _ => Web4Response::status(404),
        }
    }
}

fn simulate_replay(flap_frames: &[u16], frames: Option<u16>) -> SimulationResult {
    let normalized_flap_frames = normalize_flap_frames(flap_frames);
    let requested_frames = frames.unwrap_or(MAX_FRAMES);
    assert!(
        requested_frames <= MAX_FRAMES,
        "frames must be <= {}",
        MAX_FRAMES
    );

    let mut state = initial_state();
    let mut collision = None;
    let mut flap_cursor = 0usize;

    while state.alive && state.frame < requested_frames {
        let flap = flap_cursor < normalized_flap_frames.len()
            && normalized_flap_frames[flap_cursor] == state.frame;
        if flap {
            flap_cursor += 1;
        }

        if let Some(reason) = step_state(&mut state, flap) {
            collision = Some(reason);
        }
    }

    SimulationResult {
        visible_pipes: collect_visible_pipes(state.frame, 4),
        frames_simulated: state.frame,
        final_state: state,
        collision,
        normalized_flap_frames,
    }
}

fn initial_state() -> GameState {
    GameState {
        frame: 0,
        bird_y: INITIAL_BIRD_Y,
        velocity: INITIAL_VELOCITY,
        score: 0,
        next_pipe_index: 0,
        alive: true,
    }
}

fn step_state(state: &mut GameState, flap: bool) -> Option<String> {
    if flap {
        state.velocity = FLAP_VELOCITY;
    }
    state.velocity = (state.velocity + GRAVITY).min(MAX_FALL_VELOCITY);
    state.bird_y += state.velocity;
    state.frame += 1;

    while build_pipe_at(state.next_pipe_index, state.frame).x + PIPE_WIDTH < BIRD_X - BIRD_RADIUS {
        state.score += 1;
        state.next_pipe_index += 1;
    }

    if state.bird_y - BIRD_RADIUS * SCALE <= 0 {
        state.alive = false;
        return Some("ceiling".to_string());
    }

    if state.bird_y + BIRD_RADIUS * SCALE >= SKY_HEIGHT * SCALE {
        state.alive = false;
        return Some("ground".to_string());
    }

    for pipe in collect_visible_pipes(state.frame, 4) {
        let bird_y = state.bird_y / SCALE;
        let overlaps_x =
            BIRD_X + BIRD_RADIUS > pipe.x && BIRD_X - BIRD_RADIUS < pipe.x + PIPE_WIDTH;
        let outside_gap =
            bird_y - BIRD_RADIUS < pipe.gap_top || bird_y + BIRD_RADIUS > pipe.gap_bottom;
        if overlaps_x && outside_gap {
            state.alive = false;
            return Some(format!("pipe_{}", pipe.index));
        }
    }

    None
}

fn normalize_flap_frames(flap_frames: &[u16]) -> Vec<u16> {
    assert!(
        flap_frames.len() <= MAX_FLAPS,
        "at most {} flap frames are allowed",
        MAX_FLAPS
    );
    let mut normalized = flap_frames
        .iter()
        .copied()
        .filter(|frame| *frame < MAX_FRAMES)
        .collect::<Vec<_>>();
    normalized.sort_unstable();
    normalized.dedup();
    normalized
}

fn build_pipe_at(index: u16, frame: u16) -> Pipe {
    let x = PIPE_START_X + index as i32 * PIPE_SPACING - frame as i32 * PIPE_SCROLL_SPEED;
    let gap_center_y = gap_center_y(index);
    Pipe {
        index,
        x,
        gap_center_y,
        gap_top: gap_center_y - PIPE_GAP / 2,
        gap_bottom: gap_center_y + PIPE_GAP / 2,
    }
}

fn collect_visible_pipes(frame: u16, count: usize) -> Vec<Pipe> {
    let earliest_visible = ((frame as i32 * PIPE_SCROLL_SPEED - PIPE_START_X - PIPE_WIDTH)
        / PIPE_SPACING)
        .max(0) as u16;
    let mut pipes = Vec::new();
    let scan_limit = earliest_visible as usize + count + 8;
    for index in earliest_visible as usize..scan_limit {
        let pipe = build_pipe_at(index as u16, frame);
        if pipe.x < CANVAS_WIDTH + PIPE_SPACING && pipe.x + PIPE_WIDTH > -PIPE_SPACING {
            pipes.push(pipe);
            if pipes.len() == count {
                break;
            }
        }
    }
    pipes
}

fn gap_center_y(index: u16) -> i32 {
    let min = PIPE_MARGIN + PIPE_GAP / 2;
    let max = SKY_HEIGHT - PIPE_MARGIN - PIPE_GAP / 2;
    let span = (max - min + 1) as u32;
    let mixed = splitmix32(index as u32 + 0x6d2b_79f5);
    min + (mixed % span) as i32
}

fn splitmix32(mut value: u32) -> u32 {
    value = value.wrapping_add(0x9e37_79b9);
    value = (value ^ (value >> 16)).wrapping_mul(0x85eb_ca6b);
    value = (value ^ (value >> 13)).wrapping_mul(0xc2b2_ae35);
    value ^ (value >> 16)
}

fn sanitize_display_name(name: String) -> String {
    let cleaned = name
        .chars()
        .filter(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
        .take(24)
        .collect::<String>();
    if cleaned.is_empty() {
        "player".to_string()
    } else {
        cleaned
    }
}

fn render_web4_page(contract_id: &str) -> String {
    let html = r###"<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IronClaw Flappy on NEAR</title>
  <style>
    :root {
      --ink: #111111;
      --muted: rgba(0, 0, 0, 0.56);
      --page: #f6f6f6;
      --hero: #f6f6f6;
      --panel: rgba(255, 255, 255, 0.76);
      --line: rgba(0, 0, 0, 0.08);
      --blue: #4ca7e6;
      --blue-deep: #2882c8;
      --blue-soft: rgba(76, 167, 230, 0.14);
      --danger: #ff6a57;
      --shadow: 0 22px 64px rgba(17, 17, 17, 0.1);
      --soft-shadow: 0 14px 48px rgba(76, 167, 230, 0.18);
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Gill Sans", "Trebuchet MS", sans-serif;
      background:
        radial-gradient(circle at center, rgba(76, 167, 230, 0.34) 1px, transparent 1px) 0 0 / 18px 18px,
        radial-gradient(ellipse 70% 46% at 50% 100%, rgba(76, 167, 230, 0.12), transparent 70%),
        var(--page);
    }
    .shell {
      width: min(1340px, calc(100vw - 28px));
      min-height: calc(100vh - 28px);
      margin: 0 auto;
      padding: 34px 0;
      display: grid;
      grid-template-columns: 320px minmax(288px, 1fr) 300px;
      gap: 18px;
      align-items: stretch;
    }
    .rail, .scoreboard {
      background: var(--hero);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 8px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .scoreboard {
      position: relative;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.72);
      color: var(--ink);
      border-color: rgba(76, 167, 230, 0.28);
      box-shadow: 0 18px 58px rgba(76, 167, 230, 0.14);
      backdrop-filter: blur(8px);
    }
    .scoreboard::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 4px;
      background: linear-gradient(90deg, var(--blue), transparent);
    }
    .eyebrow {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border: 1px solid rgba(76, 167, 230, 0.32);
      border-radius: 999px;
      background: var(--blue-soft);
      color: var(--ink);
      font-family: "Courier New", monospace;
      font-size: 0.72rem;
      text-transform: uppercase;
    }
    .eyebrow::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--blue);
      box-shadow: 0 0 0 5px rgba(76, 167, 230, 0.14);
    }
    .brand {
      margin: 0;
      font-size: clamp(2rem, 3.2vw, 3rem);
      line-height: 0.96;
      letter-spacing: 0;
      font-weight: 800;
    }
    .brand .accent {
      display: block;
      color: var(--blue-deep);
    }
    .tag {
      margin: 0;
      color: var(--muted);
      line-height: 1.35;
      font-size: 0.98rem;
    }
    .statline {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: baseline;
      padding-top: 10px;
      border-top: 1px solid var(--line);
    }
    .scoreboard .statline { border-color: rgba(0, 0, 0, 0.08); }
    .statline span {
      color: var(--muted);
      font-family: "Courier New", monospace;
      font-size: 0.72rem;
      text-transform: uppercase;
    }
    .scoreboard .statline span { color: rgba(0, 0, 0, 0.46); }
    .statline strong { font-size: 1.32rem; }
    button {
      min-height: 46px;
      border: 2px solid rgba(76, 167, 230, 0.54);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.08);
      color: var(--ink);
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, box-shadow 160ms ease, border-color 160ms ease;
    }
    button.primary {
      border-color: transparent;
      background: radial-gradient(ellipse 100% 110% at 50% 130%, var(--blue) 0%, var(--blue-deep) 68%);
      color: #ffffff;
      box-shadow: var(--soft-shadow);
    }
    button:hover { border-color: var(--blue); box-shadow: 0 10px 28px rgba(76, 167, 230, 0.18); }
    button:active { transform: translateY(2px); }
    .stage-wrap {
      display: grid;
      place-items: center;
      min-width: 0;
      background:
        radial-gradient(ellipse 75% 48% at 50% 100%, rgba(76, 167, 230, 0.18), transparent 72%),
        var(--hero);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }
    .stage {
      width: min(100%, 420px);
      aspect-ratio: 288 / 512;
      image-rendering: pixelated;
      border-radius: 8px;
      border: 2px solid rgba(0, 0, 0, 0.16);
      background: #f6f6f6;
      box-shadow: 0 24px 56px rgba(0, 0, 0, 0.22);
      touch-action: manipulation;
    }
    .meter {
      height: 8px;
      background: rgba(0, 0, 0, 0.08);
      border-radius: 99px;
      overflow: hidden;
    }
    .meter div {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--blue), #5bbaf5, var(--danger));
      transition: width 120ms linear;
    }
    .status {
      min-height: 42px;
      color: var(--muted);
      line-height: 1.35;
      font-size: 0.92rem;
    }
    .scoreboard .status { color: var(--muted); }
    .leader-title {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
    }
    .leader-title h2 {
      margin: 0;
      font-size: 1.35rem;
      letter-spacing: 0;
      font-weight: 800;
    }
    .leader-title span { color: rgba(0, 0, 0, 0.44); font-size: 0.78rem; }
    .leaders {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .leaders li {
      display: grid;
      grid-template-columns: 28px 1fr auto;
      gap: 8px;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid rgba(0, 0, 0, 0.08);
      font-size: 0.92rem;
    }
    .leaders span { color: rgba(0, 0, 0, 0.46); }
    .leaders b {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .score-modal {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      place-items: center;
      padding: 20px;
      background: rgba(0, 0, 0, 0.62);
    }
    .score-modal.open { display: grid; }
    .score-dialog {
      width: min(360px, 100%);
      background: var(--hero);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 20px;
      display: grid;
      gap: 14px;
    }
    .score-dialog h2 {
      margin: 0;
      font-size: 1.8rem;
      letter-spacing: 0;
    }
    .score-dialog .final-score {
      font-size: 4rem;
      line-height: 0.9;
      font-weight: 800;
      color: var(--blue-deep);
    }
    .score-dialog p {
      margin: 0;
      color: var(--muted);
      line-height: 1.35;
    }
    .score-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .mono { font-family: "Courier New", monospace; font-size: 0.86rem; }
    @media (max-width: 900px) {
      .shell {
        grid-template-columns: 1fr;
        min-height: auto;
        padding: 18px 0;
      }
      .rail, .scoreboard {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .brand, .tag, .status, .leader-title, .leaders { grid-column: 1 / -1; }
      .stage-wrap { order: -1; }
    }
    @media (max-width: 520px) {
      .shell { width: min(100vw - 16px, 420px); padding: 8px 0 16px; gap: 10px; }
      .rail, .scoreboard { grid-template-columns: 1fr; padding: 12px; }
      .stage-wrap { padding: 8px; }
      .brand { font-size: 1.8rem; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="rail">
      <div class="eyebrow">NEAR TESTNET</div>
      <h1 class="brand"><span class="accent">IronClaw</span> Flappy</h1>
      <p class="tag">Replay-verified arcade physics, served from a NEAR contract.</p>
      <button id="start" class="primary">Start</button>
      <button id="verify">Verify</button>
      <button id="connect-wallet">Link NEAR</button>
      <button id="submit-score">Submit Score</button>
      <button id="reset">Reset</button>
      <div class="statline"><span>Score</span><strong id="score">0</strong></div>
      <div class="statline"><span>Frame</span><strong id="frame">0</strong></div>
      <div class="statline"><span>Flaps</span><strong id="flaps">0</strong></div>
    </section>

    <section class="stage-wrap">
      <canvas id="stage" class="stage" width="288" height="512" aria-label="Flappy On NEAR game"></canvas>
    </section>

    <aside class="scoreboard">
      <div class="leader-title">
        <h2>Chain Board</h2>
        <span id="contract" class="mono">__CONTRACT_ID__</span>
      </div>
      <div class="statline"><span>Verifier</span><strong id="verifier">idle</strong></div>
      <div class="meter"><div id="meter"></div></div>
      <p id="status" class="status">Ready.</p>
      <ol id="leaders" class="leaders"></ol>
    </aside>
  </main>

  <div id="score-modal" class="score-modal" role="dialog" aria-modal="true" aria-labelledby="score-modal-title">
    <div class="score-dialog">
      <h2 id="score-modal-title">Run Complete</h2>
      <div id="modal-score" class="final-score">0</div>
      <p id="modal-copy">Submit this replay to the on-chain board.</p>
      <div class="score-actions">
        <button id="modal-submit" class="primary">Submit</button>
        <button id="modal-close">Close</button>
      </div>
    </div>
  </div>

  <script>
    const contractId = '__CONTRACT_ID__';
    const isTestnet = contractId.endsWith('.testnet');
    const rpcUrl = isTestnet ? 'https://rpc.testnet.near.org' : 'https://rpc.mainnet.near.org';
    const C = {
      scale: __SCALE__,
      width: __CANVAS_WIDTH__,
      height: __CANVAS_HEIGHT__,
      skyHeight: __SKY_HEIGHT__,
      birdX: __BIRD_X__,
      birdRadius: __BIRD_RADIUS__,
      initialBirdY: __INITIAL_BIRD_Y__,
      flapVelocity: __FLAP_VELOCITY__,
      gravity: __GRAVITY__,
      maxFallVelocity: __MAX_FALL_VELOCITY__,
      pipeWidth: __PIPE_WIDTH__,
      pipeGap: __PIPE_GAP__,
      pipeSpacing: __PIPE_SPACING__,
      pipeStartX: __PIPE_START_X__,
      pipeScrollSpeed: __PIPE_SCROLL_SPEED__,
      maxFrames: __MAX_FRAMES__
    };

    const canvas = document.getElementById('stage');
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    const scoreEl = document.getElementById('score');
    const frameEl = document.getElementById('frame');
    const flapsEl = document.getElementById('flaps');
    const statusEl = document.getElementById('status');
    const verifierEl = document.getElementById('verifier');
    const meterEl = document.getElementById('meter');
    const leadersEl = document.getElementById('leaders');
    const startButton = document.getElementById('start');
    const verifyButton = document.getElementById('verify');
    const connectWalletButton = document.getElementById('connect-wallet');
    const submitScoreButton = document.getElementById('submit-score');
    const resetButton = document.getElementById('reset');
    const scoreModal = document.getElementById('score-modal');
    const modalScoreEl = document.getElementById('modal-score');
    const modalCopyEl = document.getElementById('modal-copy');
    const modalSubmitButton = document.getElementById('modal-submit');
    const modalCloseButton = document.getElementById('modal-close');

    let state = freshState();
    let flapFrames = [];
    let running = false;
    let lastTick = 0;
    let rafId = null;
    let verifyInFlight = false;
    let nearConnector = null;
    let connectedWallet = null;
    let connectedAccountId = null;
    let scoreModalShownForFrame = null;
    let ironclawSprite = null;
    const pendingReplayKey = 'flappy:onchain:pendingReplay:' + contractId;

    function freshState() {
      return {
        frame: 0,
        birdY: C.initialBirdY,
        velocity: 0,
        score: 0,
        nextPipeIndex: 0,
        alive: true
      };
    }

    function encodeArgs(args) {
      const bytes = new TextEncoder().encode(JSON.stringify(args));
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      return btoa(binary);
    }

    async function viewCall(methodName, args) {
      const response = await fetch(rpcUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 'web4-flappy',
          method: 'query',
          params: {
            request_type: 'call_function',
            finality: 'final',
            account_id: contractId,
            method_name: methodName,
            args_base64: encodeArgs(args)
          }
        })
      });
      const json = await response.json();
      if (json.error) throw new Error(json.error.data || json.error.message || 'RPC error');
      return JSON.parse(new TextDecoder().decode(new Uint8Array(json.result.result)));
    }

    function splitmix32(value) {
      value = (value + 0x9e3779b9) >>> 0;
      value = Math.imul(value ^ (value >>> 16), 0x85ebca6b) >>> 0;
      value = Math.imul(value ^ (value >>> 13), 0xc2b2ae35) >>> 0;
      return (value ^ (value >>> 16)) >>> 0;
    }

    function gapCenterY(index) {
      const min = 54 + C.pipeGap / 2;
      const max = C.skyHeight - 54 - C.pipeGap / 2;
      const span = max - min + 1;
      return min + (splitmix32((index + 0x6d2b79f5) >>> 0) % span);
    }

    function pipeAt(index, frame) {
      const gapCenter = gapCenterY(index);
      return {
        index,
        x: C.pipeStartX + index * C.pipeSpacing - frame * C.pipeScrollSpeed,
        gapTop: gapCenter - C.pipeGap / 2,
        gapBottom: gapCenter + C.pipeGap / 2
      };
    }

    function visiblePipes(frame, count = 4) {
      const start = Math.max(0, Math.trunc((frame * C.pipeScrollSpeed - C.pipeStartX - C.pipeWidth) / C.pipeSpacing));
      const pipes = [];
      for (let index = start; pipes.length < count && index < start + count + 8; index += 1) {
        const pipe = pipeAt(index, frame);
        if (pipe.x < C.width + C.pipeSpacing && pipe.x + C.pipeWidth > -C.pipeSpacing) pipes.push(pipe);
      }
      return pipes;
    }

    const spritePalette = {
      '.': null,
      'K': '#111111',
      'O': '#1f6fa8',
      'Y': '#4ca7e6',
      'L': '#8ed3ff',
      'C': '#d8efff',
      'R': '#ff6a57',
      'W': '#ffffff',
      'P': '#5bbaf5',
      'G': '#2882c8',
      'H': '#69c2ff',
      'D': '#0d3755',
      'M': '#dceefa',
      'S': '#bcd7e8',
      'B': '#2a2a2a',
      'T': '#111111',
      'Q': '#ffffff'
    };
    const birdSprites = [
      [
        '.....KKKKKK......',
        '...KKYYYYYYKK....',
        '..KYYYYYYYYYYK...',
        '.KYYLLYYYYWWWK...',
        'KYYLLLLYYWKKWK...',
        'KYYLLLLYYYYYWKRR.',
        'KYYYYYYYYYYYYKRRR',
        'KYYYCCCCYYYYYKRR.',
        '.KYYCCCCYYYYK....',
        '..KYYYYYYYYK.....',
        '...KKYYYYKK......',
        '.....KPPK........',
        '....KPOOPK.......',
        '.....KKKK........'
      ],
      [
        '.....KKKKKK......',
        '...KKYYYYYYKK....',
        '..KYYYYYYYYYYK...',
        '.KYYLLYYYYWWWK...',
        'KYYLLLLYYWKKWK...',
        'KYYLLLLYYYYYWKRR.',
        'KYYYYYYYYYYYYKRRR',
        'KYYYYYYYYYYYYKRR.',
        '.KYYCCCCYYYYK....',
        '..KCCCCCCYYK.....',
        '.KCCCCCCCCK......',
        'KCCCCCCCK........',
        '.KKKKKKK.........',
        '.................'
      ],
      [
        '.....KKKKKK......',
        '...KKYYYYYYKK....',
        '..KYYYYYYYYYYK...',
        '.KYYLLYYYYWWWK...',
        'KYYLLLLYYWKKWK...',
        'KYYLLLLYYYYYWKRR.',
        'KYYYYYYYYYYYYKRRR',
        'KYYYCCCCYYYYYKRR.',
        '.KYYCCCCYYYYK....',
        '..KYYYYYYYYK.....',
        '...KKYYYYKK......',
        '.....KCCK........',
        '....KCCCCK.......',
        '...KCCCCCCK......',
        '....KKKKKK.......'
      ]
    ];
    const cloudSprite = [
      '...QQQQ.........',
      '.QQQQQQQQ.......',
      'QQQQQQQQQQ..QQQ.',
      'QQQQQQQQQQQQQQQQ',
      '.QQQQQQQQQQQQQQ.',
      '...QQQQQQQQQQ...'
    ];
    const groundTile = [
      'MMMMSSMMMMSSMMMMSSMMMMSS',
      'SSMMSSSSMMSSSSMMSSSSMMSS',
      'BBBBBBBBBBBBBBBBBBBBBBBB',
      'BTBTBBBBTBTBBBBTBTBBBBT',
      'BBBBTBTBBBBTBTBBBBTBTBB',
      'TTBBBBTTBBBBTTBBBBTTBBBB'
    ];

    function drawPixelSprite(sprite, x, y, pixelSize, palette = spritePalette) {
      for (let row = 0; row < sprite.length; row += 1) {
        const line = sprite[row];
        for (let col = 0; col < line.length; col += 1) {
          const color = palette[line[col]];
          if (!color) continue;
          ctx.fillStyle = color;
          ctx.fillRect(Math.round(x + col * pixelSize), Math.round(y + row * pixelSize), pixelSize, pixelSize);
        }
      }
    }

    function drawPixelCloud(x, y, scale) {
      ctx.globalAlpha = 0.62;
      drawPixelSprite(cloudSprite, x, y, scale);
      ctx.globalAlpha = 1;
    }

    function drawGround() {
      ctx.fillStyle = '#111111';
      ctx.fillRect(0, C.skyHeight, C.width, C.height - C.skyHeight);
      const tileWidth = groundTile[0].length * 3;
      const offset = -((state.frame * C.pipeScrollSpeed) % tileWidth);
      for (let x = offset; x < C.width + tileWidth; x += tileWidth) {
        drawPixelSprite(groundTile, x, C.skyHeight, 3);
      }
    }

    function loadIronclawSprite() {
      const image = new Image();
      image.onload = () => {
        ironclawSprite = image;
        draw();
      };
      image.src = '/ironclaw-sprite.png';
    }

    function localStep(flap) {
      if (flap) state.velocity = C.flapVelocity;
      state.velocity = Math.min(state.velocity + C.gravity, C.maxFallVelocity);
      state.birdY += state.velocity;
      state.frame += 1;
      while (pipeAt(state.nextPipeIndex, state.frame).x + C.pipeWidth < C.birdX - C.birdRadius) {
        state.score += 1;
        state.nextPipeIndex += 1;
      }
      if (state.birdY - C.birdRadius * C.scale <= 0 || state.birdY + C.birdRadius * C.scale >= C.skyHeight * C.scale) {
        state.alive = false;
      }
      const birdY = Math.trunc(state.birdY / C.scale);
      for (const pipe of visiblePipes(state.frame)) {
        const overlapsX = C.birdX + C.birdRadius > pipe.x && C.birdX - C.birdRadius < pipe.x + C.pipeWidth;
        const outsideGap = birdY - C.birdRadius < pipe.gapTop || birdY + C.birdRadius > pipe.gapBottom;
        if (overlapsX && outsideGap) state.alive = false;
      }
    }

    function draw() {
      ctx.clearRect(0, 0, C.width, C.height);
      const sky = ctx.createLinearGradient(0, 0, 0, C.skyHeight);
      sky.addColorStop(0, '#f6f6f6');
      sky.addColorStop(0.62, '#e9f5fe');
      sky.addColorStop(1, '#d8efff');
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, C.width, C.skyHeight);
      ctx.fillStyle = 'rgba(76, 167, 230, 0.08)';
      for (let y = 22; y < C.skyHeight; y += 36) ctx.fillRect(0, y, C.width, 1);
      for (let x = -((state.frame * 0.4) % 88); x < C.width + 80; x += 88) {
        drawPixelCloud(x + 18, 58, 3);
        drawPixelCloud(x + 78, 128, 2);
      }
      for (const pipe of visiblePipes(state.frame)) {
        drawPipe(pipe.x, 0, C.pipeWidth, pipe.gapTop, true);
        drawPipe(pipe.x, pipe.gapBottom, C.pipeWidth, C.skyHeight - pipe.gapBottom, false);
      }
      drawGround();
      drawBird();
      if (!running && state.frame === 0) drawSplash('START');
      if (!state.alive) drawSplash(String(state.score));
      scoreEl.textContent = state.score;
      frameEl.textContent = state.frame;
      flapsEl.textContent = flapFrames.length;
      meterEl.style.width = Math.min(100, (state.frame / C.maxFrames) * 100) + '%';
    }

    function drawPipe(x, y, width, height, flip) {
      if (height <= 0) return;
      const px = Math.round(x);
      const py = Math.round(y);
      const h = Math.round(height);
      ctx.fillStyle = '#0d3755';
      ctx.fillRect(px, py, width, h);
      ctx.fillStyle = '#2882c8';
      ctx.fillRect(px + 3, py, width - 9, h);
      ctx.fillStyle = '#69c2ff';
      for (let yy = py + 4; yy < py + h; yy += 16) {
        ctx.fillRect(px + 8, yy, 8, 10);
        ctx.fillRect(px + 24, yy + 4, 6, 8);
      }
      ctx.fillStyle = '#0b2a40';
      for (let yy = py; yy < py + h; yy += 8) {
        ctx.fillRect(px + width - 8, yy, 5, 4);
      }
      const lipY = flip ? y + height - 12 : y;
      ctx.fillStyle = '#0d3755';
      ctx.fillRect(px - 4, Math.round(lipY), width + 8, 16);
      ctx.fillStyle = '#2882c8';
      ctx.fillRect(px, Math.round(lipY) + 3, width, 10);
      ctx.fillStyle = '#8ed3ff';
      ctx.fillRect(px + 7, Math.round(lipY) + 5, 12, 4);
      ctx.strokeStyle = '#111111';
      ctx.lineWidth = 2;
      ctx.strokeRect(px - 4, Math.round(lipY), width + 8, 16);
    }

    function drawBird() {
      const y = Math.trunc(state.birdY / C.scale);
      ctx.save();
      ctx.translate(C.birdX, y);
      ctx.rotate(Math.max(-0.45, Math.min(0.75, state.velocity / 11000)));
      if (ironclawSprite) {
        const width = 58;
        const height = Math.round(width * ironclawSprite.height / ironclawSprite.width);
        ctx.drawImage(ironclawSprite, -width / 2, -height / 2, width, height);
      } else {
        const flapIndex = state.alive ? Math.trunc(state.frame / 6) % birdSprites.length : 1;
        drawPixelSprite(birdSprites[flapIndex], -17, -14, 2);
      }
      ctx.restore();
    }

    function drawSplash(text) {
      ctx.fillStyle = 'rgba(246, 246, 246, 0.92)';
      ctx.fillRect(42, 184, 204, 82);
      ctx.strokeStyle = '#4ca7e6';
      ctx.lineWidth = 3;
      ctx.strokeRect(42, 184, 204, 82);
      ctx.fillStyle = '#111111';
      ctx.font = '800 34px Avenir Next, Trebuchet MS, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(text, 144, 236);
    }

    function flap() {
      if (!running) startGame();
      if (!state.alive) return;
      if (flapFrames[flapFrames.length - 1] !== state.frame) flapFrames.push(state.frame);
    }

    function startGame() {
      if (!state.alive) resetGame();
      running = true;
      lastTick = performance.now();
      statusEl.textContent = 'Running.';
      startButton.textContent = 'Flap';
      if (!rafId) rafId = requestAnimationFrame(loop);
    }

    function resetGame() {
      closeScoreModal();
      state = freshState();
      flapFrames = [];
      running = false;
      startButton.textContent = 'Start';
      verifierEl.textContent = 'idle';
      statusEl.textContent = 'Ready.';
      draw();
    }

    function loop(now) {
      rafId = requestAnimationFrame(loop);
      const elapsed = now - lastTick;
      if (!running || elapsed < 1000 / 60) {
        draw();
        return;
      }
      lastTick = now;
      const shouldFlap = flapFrames[flapFrames.length - 1] === state.frame;
      localStep(shouldFlap);
      if (state.frame % 90 === 0) verifyReplay(false);
      if (!state.alive || state.frame >= C.maxFrames) {
        running = false;
        startButton.textContent = 'Start';
        verifyReplay(true);
        showScoreModal();
      }
      draw();
    }

    async function verifyReplay(finalRun) {
      if (verifyInFlight) return;
      verifyInFlight = true;
      verifierEl.textContent = '...';
      try {
        const result = await viewCall('simulate', {
          flap_frames: flapFrames,
          frames: finalRun ? null : state.frame
        });
        const chainState = result.final_state;
        const matches = chainState.frame === state.frame &&
          chainState.score === state.score &&
          chainState.bird_y === state.birdY &&
          chainState.alive === state.alive;
        verifierEl.textContent = matches ? 'match' : 'diff';
        statusEl.textContent = finalRun
          ? 'Chain score ' + chainState.score + ' at frame ' + chainState.frame + '.'
          : 'Verified frame ' + chainState.frame + '.';
      } catch (error) {
        verifierEl.textContent = 'offline';
        statusEl.textContent = error.message;
      } finally {
        verifyInFlight = false;
      }
    }

    async function loadLeaderboard() {
      try {
        const rows = await viewCall('leaderboard', {});
        leadersEl.innerHTML = '';
        if (!rows.length) {
          const item = document.createElement('li');
          item.innerHTML = '<span>-</span><b>no entries</b><span>0</span>';
          leadersEl.appendChild(item);
          return;
        }
        rows.forEach((row, index) => {
          const item = document.createElement('li');
          const rank = document.createElement('span');
          rank.textContent = String(index + 1);
          const name = document.createElement('b');
          name.textContent = row.display_name;
          const score = document.createElement('span');
          score.textContent = row.score;
          item.append(rank, name, score);
          leadersEl.appendChild(item);
        });
      } catch (error) {
        leadersEl.innerHTML = '<li><span>-</span><b>unavailable</b><span>0</span></li>';
      }
    }

    function updateWalletUi() {
      connectWalletButton.textContent = connectedAccountId ? connectedAccountId : 'Link NEAR';
      if (scoreModal.classList.contains('open')) {
        modalSubmitButton.textContent = connectedAccountId ? 'Submit' : 'Link + Submit';
        modalCopyEl.textContent = connectedAccountId
          ? 'Submit this replay as ' + connectedAccountId + '.'
          : 'Link a NEAR account to submit this replay.';
      }
    }

    function showScoreModal() {
      if (scoreModalShownForFrame === state.frame) return;
      scoreModalShownForFrame = state.frame;
      modalScoreEl.textContent = state.score;
      scoreModal.classList.add('open');
      updateWalletUi();
    }

    function closeScoreModal() {
      scoreModal.classList.remove('open');
    }

    async function initWallet() {
      if (nearConnector) return nearConnector;
      try {
        const { NearConnector } = await import('/near-connect.mjs');
        nearConnector = new NearConnector({
          network: isTestnet ? 'testnet' : 'mainnet',
          features: {
            signInWithoutAddKey: true,
            signAndSendTransaction: true
          },
          footerBranding: null
        });
        nearConnector.on('wallet:signIn', async ({ wallet, accounts, success }) => {
          if (!success || !accounts.length) return;
          connectedWallet = wallet;
          connectedAccountId = accounts[0].accountId;
          updateWalletUi();
          statusEl.textContent = 'Linked as ' + connectedAccountId + '.';
          await submitPendingReplay();
        });
        nearConnector.on('wallet:signOut', () => {
          connectedWallet = null;
          connectedAccountId = null;
          updateWalletUi();
        });
        try {
          const session = await nearConnector.getConnectedWallet();
          connectedWallet = session.wallet;
          connectedAccountId = session.accounts[0]?.accountId || null;
          updateWalletUi();
        } catch (_) {}
        await submitPendingReplay();
      } catch (error) {
        statusEl.textContent = 'Wallet connector failed: ' + error.message;
      }
      return nearConnector;
    }

    async function connectWallet() {
      const connector = await initWallet();
      if (!connector) return;
      if (connectedAccountId) {
        statusEl.textContent = 'Linked as ' + connectedAccountId + '.';
        return;
      }
      try {
        const wallet = await connector.connect();
        connectedWallet = wallet;
        const accounts = await wallet.getAccounts({ network: isTestnet ? 'testnet' : 'mainnet' });
        connectedAccountId = accounts[0]?.accountId || null;
        updateWalletUi();
        if (connectedAccountId) {
          statusEl.textContent = 'Linked as ' + connectedAccountId + '.';
          await submitPendingReplay();
        }
      } catch (error) {
        statusEl.textContent = 'Wallet link failed: ' + error.message;
      }
    }

    function currentReplay() {
      return {
        flapFrames: Array.from(flapFrames),
        score: state.score,
        frame: state.frame
      };
    }

    async function submitPendingReplay() {
      const pending = localStorage.getItem(pendingReplayKey);
      if (!pending || !connectedAccountId) return;
      localStorage.removeItem(pendingReplayKey);
      await submitReplay(JSON.parse(pending));
    }

    async function submitCurrentScore() {
      if (running || state.alive) {
        statusEl.textContent = 'Finish the run before submitting.';
        return;
      }
      const replay = currentReplay();
      if (!connectedAccountId) {
        localStorage.setItem(pendingReplayKey, JSON.stringify(replay));
        statusEl.textContent = 'Link a NEAR account to submit this score.';
        await connectWallet();
        return;
      }
      await submitReplay(replay);
    }

    async function submitReplay(replay) {
      const connector = await initWallet();
      if (!connector || !connectedAccountId) return;
      submitScoreButton.disabled = true;
      statusEl.textContent = 'Submitting score for ' + connectedAccountId + '...';
      try {
        connectedWallet = connectedWallet || await connector.wallet();
        await connectedWallet.signAndSendTransaction({
          network: isTestnet ? 'testnet' : 'mainnet',
          signerId: connectedAccountId,
          receiverId: contractId,
          actions: [
            {
              type: 'FunctionCall',
              params: {
                methodName: 'submit_score',
                args: {
                  flap_frames: replay.flapFrames,
                  display_name: connectedAccountId
                },
                gas: '30000000000000',
                deposit: '0'
              }
            }
          ],
          callbackUrl: window.location.origin + window.location.pathname
        });
        statusEl.textContent = 'Score submitted.';
        closeScoreModal();
        await loadLeaderboard();
      } catch (error) {
        statusEl.textContent = 'Submit failed: ' + error.message;
      } finally {
        submitScoreButton.disabled = false;
        updateWalletUi();
      }
    }

    startButton.addEventListener('click', flap);
    verifyButton.addEventListener('click', () => verifyReplay(!state.alive));
    connectWalletButton.addEventListener('click', connectWallet);
    submitScoreButton.addEventListener('click', submitCurrentScore);
    modalSubmitButton.addEventListener('click', submitCurrentScore);
    modalCloseButton.addEventListener('click', closeScoreModal);
    scoreModal.addEventListener('click', (event) => {
      if (event.target === scoreModal) closeScoreModal();
    });
    resetButton.addEventListener('click', resetGame);
    canvas.addEventListener('pointerdown', flap);
    window.addEventListener('keydown', (event) => {
      if (event.code === 'Space' || event.code === 'ArrowUp') {
        event.preventDefault();
        flap();
      }
    });

    loadIronclawSprite();
    draw();
    loadLeaderboard();
    initWallet();
  </script>
</body>
</html>"###;

    html.replace("__CONTRACT_ID__", contract_id)
        .replace("__SCALE__", &SCALE.to_string())
        .replace("__CANVAS_WIDTH__", &CANVAS_WIDTH.to_string())
        .replace("__CANVAS_HEIGHT__", &CANVAS_HEIGHT.to_string())
        .replace("__SKY_HEIGHT__", &SKY_HEIGHT.to_string())
        .replace("__BIRD_X__", &BIRD_X.to_string())
        .replace("__BIRD_RADIUS__", &BIRD_RADIUS.to_string())
        .replace("__INITIAL_BIRD_Y__", &INITIAL_BIRD_Y.to_string())
        .replace("__FLAP_VELOCITY__", &FLAP_VELOCITY.to_string())
        .replace("__GRAVITY__", &GRAVITY.to_string())
        .replace("__MAX_FALL_VELOCITY__", &MAX_FALL_VELOCITY.to_string())
        .replace("__PIPE_WIDTH__", &PIPE_WIDTH.to_string())
        .replace("__PIPE_GAP__", &PIPE_GAP.to_string())
        .replace("__PIPE_SPACING__", &PIPE_SPACING.to_string())
        .replace("__PIPE_START_X__", &PIPE_START_X.to_string())
        .replace("__PIPE_SCROLL_SPEED__", &PIPE_SCROLL_SPEED.to_string())
        .replace("__MAX_FRAMES__", &MAX_FRAMES.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_flaps_eventually_hits_ground() {
        let contract = FlappyBirdContract::new();
        let result = contract.simulate(vec![], None);

        assert!(!result.final_state.alive);
        assert_eq!(result.collision, Some("ground".to_string()));
        assert_eq!(result.final_state.score, 0);
    }

    #[test]
    fn replay_is_normalized_and_deterministic() {
        let contract = FlappyBirdContract::new();
        let unordered = contract.simulate(vec![42, 12, 12, 280, 120], Some(180));
        let ordered = contract.simulate(vec![12, 42, 120, 280], Some(180));

        assert_eq!(unordered.normalized_flap_frames, vec![12, 42, 120, 280]);
        assert_eq!(unordered.final_state.frame, ordered.final_state.frame);
        assert_eq!(unordered.final_state.bird_y, ordered.final_state.bird_y);
        assert_eq!(unordered.final_state.velocity, ordered.final_state.velocity);
        assert_eq!(unordered.final_state.score, ordered.final_state.score);
    }

    #[test]
    fn steady_replay_can_score() {
        let contract = FlappyBirdContract::new();
        let flaps = (10..1_200).step_by(31).collect::<Vec<_>>();
        let result = contract.simulate(flaps, None);

        assert!(result.final_state.score > 0);
        assert!(result.frames_simulated > 150);
    }

    #[test]
    fn exposes_expected_config() {
        let contract = FlappyBirdContract::new();
        let config = contract.game_config();

        assert_eq!(config.scale, SCALE);
        assert_eq!(config.canvas_width, 288);
        assert_eq!(config.canvas_height, 512);
        assert_eq!(config.pipe_gap, PIPE_GAP);
        assert_eq!(config.max_frames, MAX_FRAMES);
    }

    #[test]
    fn serves_web4_html() {
        let contract = FlappyBirdContract::new();
        let response = contract.web4_get(Web4Request {
            account_id: None,
            path: "/".to_string(),
            params: None,
            query: None,
        });

        match response {
            Web4Response::Body { content_type, body } => {
                assert_eq!(content_type, "text/html; charset=UTF-8");
                let html = String::from_utf8(body.0).unwrap();
                assert!(html.contains("Flappy On NEAR"));
                assert!(html.contains("simulate"));
            }
            Web4Response::Status { status } => panic!("unexpected status response: {status}"),
        }
    }

    #[test]
    fn serves_optimized_ironclaw_sprite() {
        let contract = FlappyBirdContract::new();
        let response = contract.web4_get(Web4Request {
            account_id: None,
            path: "/ironclaw-sprite.png".to_string(),
            params: None,
            query: None,
        });

        match response {
            Web4Response::Body { content_type, body } => {
                assert_eq!(content_type, "image/png");
                assert!(body.0.len() < 25_000);
                assert!(body.0.starts_with(b"\x89PNG\r\n\x1a\n"));
            }
            Web4Response::Status { status } => panic!("unexpected status response: {status}"),
        }
    }
}
