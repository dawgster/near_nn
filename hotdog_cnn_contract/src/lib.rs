mod model_data;

use std::collections::HashMap;

use near_sdk::env;
use near_sdk::json_types::Base64VecU8;
use near_sdk::serde::{Deserialize, Serialize};
use near_sdk::{near, PanicOnDefault};

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct ModelInfo {
    pub input_width: usize,
    pub input_height: usize,
    pub input_channels: usize,
    pub conv1_channels: usize,
    pub conv2_channels: usize,
    pub conv3_channels: usize,
    pub mlp_hidden_size: usize,
    pub output_size: usize,
    pub input_scale: i32,
    pub weight_scale: i32,
    pub layer_scales: Vec<i32>,
    pub sample_count: usize,
    pub labels: Vec<String>,
    pub description: String,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct Prediction {
    pub logits: Vec<i32>,
    pub predicted_index: u8,
    pub predicted_label: String,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct SamplePrediction {
    pub sample_index: u8,
    pub expected_index: u8,
    pub predicted_index: u8,
    pub predicted_label: String,
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

    fn status(status: u32) -> Self {
        Self::Status { status }
    }
}

#[derive(PanicOnDefault)]
#[near(contract_state)]
pub struct HotdogCnnContract {
    initialized: bool,
}

#[near]
impl HotdogCnnContract {
    #[init]
    pub fn new() -> Self {
        Self { initialized: true }
    }

    pub fn model_info(&self) -> ModelInfo {
        ModelInfo {
            input_width: model_data::INPUT_WIDTH,
            input_height: model_data::INPUT_HEIGHT,
            input_channels: model_data::INPUT_CHANNELS,
            conv1_channels: model_data::CONV1_OUT_CHANNELS,
            conv2_channels: model_data::CONV2_OUT_CHANNELS,
            conv3_channels: model_data::CONV3_OUT_CHANNELS,
            mlp_hidden_size: model_data::MLP_HIDDEN_SIZE,
            output_size: model_data::OUTPUT_SIZE,
            input_scale: model_data::INPUT_SCALE,
            weight_scale: model_data::CONV1_SCALE,
            layer_scales: vec![
                model_data::CONV1_SCALE,
                model_data::CONV2_SCALE,
                model_data::CONV3_SCALE,
                model_data::FC1_SCALE,
                model_data::FC2_SCALE,
            ],
            sample_count: model_data::SAMPLE_IMAGES.len(),
            labels: model_data::LABELS.iter().map(|label| label.to_string()).collect(),
            description: "Quantized RGB CNN for hotdog vs not-hotdog inference on NEAR. The model uses three 3x3 convolutions, two 2x2 max-pool stages, global average pooling, a wide ReLU MLP head, and per-layer integer scales.".to_string(),
        }
    }

    pub fn predict_pixels(&self, pixels: Vec<u8>) -> Prediction {
        assert_eq!(
            pixels.len(),
            model_data::INPUT_SIZE,
            "expected {} pixels, got {}",
            model_data::INPUT_SIZE,
            pixels.len()
        );

        let conv1 = relu_in_place(conv2d_same_stride2_u8(
            &pixels,
            model_data::INPUT_WIDTH,
            model_data::INPUT_HEIGHT,
            model_data::INPUT_CHANNELS,
            &model_data::CONV1_WEIGHTS,
            &model_data::CONV1_BIASES,
            model_data::CONV1_OUT_CHANNELS,
            model_data::INPUT_SCALE as i64,
        ));
        let pooled1 = max_pool2x2(
            &conv1,
            model_data::CONV1_WIDTH,
            model_data::CONV1_HEIGHT,
            model_data::CONV1_OUT_CHANNELS,
        );

        let conv2 = relu_in_place(conv2d_same_i32(
            &pooled1,
            model_data::POOL1_WIDTH,
            model_data::POOL1_HEIGHT,
            model_data::CONV1_OUT_CHANNELS,
            &model_data::CONV2_WEIGHTS,
            &model_data::CONV2_BIASES,
            model_data::CONV2_OUT_CHANNELS,
            model_data::CONV1_SCALE as i64,
        ));
        let pooled2 = max_pool2x2(
            &conv2,
            model_data::POOL1_WIDTH,
            model_data::POOL1_HEIGHT,
            model_data::CONV2_OUT_CHANNELS,
        );

        let conv3 = relu_in_place(conv2d_same_i32(
            &pooled2,
            model_data::POOL2_WIDTH,
            model_data::POOL2_HEIGHT,
            model_data::CONV2_OUT_CHANNELS,
            &model_data::CONV3_WEIGHTS,
            &model_data::CONV3_BIASES,
            model_data::CONV3_OUT_CHANNELS,
            model_data::CONV2_SCALE as i64,
        ));
        let pooled = global_average_pool(
            &conv3,
            model_data::POOL2_WIDTH,
            model_data::POOL2_HEIGHT,
            model_data::CONV3_OUT_CHANNELS,
        );
        let hidden = relu_in_place(linear(
            &pooled,
            &model_data::FC1_WEIGHTS,
            &model_data::FC1_BIASES,
            model_data::CONV3_OUT_CHANNELS,
            model_data::MLP_HIDDEN_SIZE,
            model_data::CONV3_SCALE as i64,
        ));
        let logits = linear(
            &hidden,
            &model_data::FC2_WEIGHTS,
            &model_data::FC2_BIASES,
            model_data::MLP_HIDDEN_SIZE,
            model_data::OUTPUT_SIZE,
            model_data::FC1_SCALE as i64,
        );

        prediction_from_logits(logits)
    }

    pub fn predict_sample(&self, sample_index: u8) -> Prediction {
        self.predict_pixels(self.sample_pixels(sample_index))
    }

    pub fn sample_pixels(&self, sample_index: u8) -> Vec<u8> {
        let index = sample_array_index(sample_index);
        model_data::SAMPLE_IMAGES[index].to_vec()
    }

    pub fn sample_predictions(&self) -> Vec<SamplePrediction> {
        model_data::SAMPLE_LABELS
            .iter()
            .enumerate()
            .map(|(idx, expected_index)| {
                let prediction = self.predict_pixels(model_data::SAMPLE_IMAGES[idx].to_vec());
                SamplePrediction {
                    sample_index: idx as u8,
                    expected_index: *expected_index,
                    predicted_index: prediction.predicted_index,
                    predicted_label: prediction.predicted_label,
                }
            })
            .collect()
    }

    pub fn web4_get(&self, request: Web4Request) -> Web4Response {
        match request.path.as_str() {
            "/" | "/index.html" => {
                Web4Response::html_response(render_web4_page(env::current_account_id().as_str()))
            }
            _ => Web4Response::status(404),
        }
    }
}

fn sample_array_index(sample_index: u8) -> usize {
    let index = sample_index as usize;
    assert!(
        index < model_data::SAMPLE_IMAGES.len(),
        "sample index must be in 0..{}",
        model_data::SAMPLE_IMAGES.len()
    );
    index
}

fn label_name(index: usize) -> &'static str {
    model_data::LABELS.get(index).copied().unwrap_or("unknown")
}

fn prediction_from_logits(logits: Vec<i32>) -> Prediction {
    let predicted_index = argmax(&logits) as u8;
    Prediction {
        predicted_label: label_name(predicted_index as usize).to_string(),
        predicted_index,
        logits,
    }
}

fn render_web4_page(contract_id: &str) -> String {
    format!(
        r##"<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>On-Chain Hotdog CNN on NEAR</title>
  <style>
    :root {{
      --bg: #f3ede2;
      --panel: rgba(255, 249, 240, 0.82);
      --ink: #1f1e1a;
      --muted: #6a6458;
      --line: rgba(31, 30, 26, 0.12);
      --accent: #d94821;
      --accent-2: #0f766e;
      --accent-3: #f2b544;
      --shadow: 0 24px 60px rgba(40, 29, 12, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 72, 33, 0.18), transparent 26%),
        radial-gradient(circle at top right, rgba(15, 118, 110, 0.18), transparent 28%),
        linear-gradient(180deg, #faf4e9 0%, #efe4d3 100%);
    }}
    .shell {{
      width: min(1180px, calc(100vw - 28px));
      margin: 18px auto 28px;
      display: grid;
      gap: 18px;
    }}
    .hero, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .hero {{
      padding: 28px;
      display: grid;
      gap: 18px;
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      color: var(--accent-2);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      max-width: 860px;
      font-size: clamp(2.6rem, 6vw, 5.2rem);
      line-height: 0.9;
      letter-spacing: -0.06em;
    }}
    .lead {{
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.7;
    }}
    .hero-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    }}
    .stat {{
      padding: 16px 18px;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.66);
      border: 1px solid rgba(31, 30, 26, 0.08);
    }}
    .stat-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.15em;
      color: var(--muted);
      font-weight: 700;
    }}
    .stat-value {{
      margin-top: 8px;
      font-size: 1.25rem;
      font-weight: 700;
      letter-spacing: -0.03em;
    }}
    .workspace {{
      display: grid;
      gap: 18px;
      grid-template-columns: minmax(340px, 460px) minmax(320px, 1fr);
    }}
    .panel {{
      padding: 22px;
    }}
    .panel h2 {{
      margin: 0 0 10px;
      font-size: 1.4rem;
      letter-spacing: -0.03em;
    }}
    .panel p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    .preview-stack {{
      margin-top: 18px;
      display: grid;
      gap: 14px;
    }}
    .preview-frame {{
      border-radius: 28px;
      padding: 18px;
      background:
        linear-gradient(145deg, rgba(217, 72, 33, 0.09), rgba(242, 181, 68, 0.08)),
        rgba(255, 255, 255, 0.74);
      border: 1px solid rgba(31, 30, 26, 0.08);
    }}
    canvas.preview {{
      width: min(100%, 320px);
      aspect-ratio: 1;
      display: block;
      margin: 0 auto;
      border-radius: 24px;
      border: 1px solid rgba(31, 30, 26, 0.14);
      box-shadow: inset 0 0 0 1px rgba(31, 30, 26, 0.05);
      background: #fff;
      image-rendering: pixelated;
    }}
    .caption-row {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .dropzone {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
      padding: 18px;
      border-radius: 22px;
      border: 1px dashed rgba(31, 30, 26, 0.18);
      background: rgba(255, 255, 255, 0.62);
    }}
    .dropzone strong {{
      font-size: 1rem;
      letter-spacing: -0.02em;
    }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    button, .file-button {{
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font: inherit;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease, box-shadow 120ms ease;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    button:hover, .file-button:hover {{ transform: translateY(-1px); }}
    button:disabled, .file-button:disabled {{
      opacity: 0.6;
      cursor: wait;
      transform: none;
    }}
    .primary {{
      color: #fff;
      background: linear-gradient(135deg, var(--accent), #ee6b2f);
      box-shadow: 0 14px 28px rgba(217, 72, 33, 0.22);
    }}
    .secondary {{
      background: rgba(15, 118, 110, 0.1);
      color: var(--accent-2);
    }}
    .ghost {{
      background: rgba(31, 30, 26, 0.06);
      color: var(--ink);
    }}
    .sample-grid {{
      margin-top: 18px;
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .sample-card {{
      text-align: left;
      border-radius: 22px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid rgba(31, 30, 26, 0.08);
      box-shadow: 0 10px 24px rgba(31, 30, 26, 0.08);
    }}
    .sample-card.active {{
      outline: 2px solid rgba(217, 72, 33, 0.4);
    }}
    .sample-card canvas {{
      width: 100%;
      aspect-ratio: 1;
      display: block;
      border-radius: 16px;
      background: #fff;
      image-rendering: pixelated;
      border: 1px solid rgba(31, 30, 26, 0.12);
    }}
    .sample-meta {{
      display: grid;
      gap: 4px;
      margin-top: 10px;
    }}
    .sample-title {{
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .sample-note {{
      font-size: 0.83rem;
      color: var(--muted);
    }}
    .result-card {{
      display: grid;
      gap: 18px;
    }}
    .headline-row {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-top: 16px;
    }}
    .verdict {{
      display: grid;
      gap: 8px;
    }}
    .verdict-badge {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 16px;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(15, 118, 110, 0.14), rgba(242, 181, 68, 0.22));
      width: fit-content;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .verdict-badge.hotdog {{
      background: linear-gradient(135deg, rgba(217, 72, 33, 0.2), rgba(242, 181, 68, 0.28));
    }}
    .verdict-badge.not-hotdog {{
      background: linear-gradient(135deg, rgba(15, 118, 110, 0.18), rgba(31, 30, 26, 0.08));
    }}
    .verdict-title {{
      font-size: clamp(1.6rem, 4vw, 3.2rem);
      font-weight: 800;
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .summary-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .chip {{
      padding: 14px;
      border-radius: 18px;
      border: 1px solid rgba(31, 30, 26, 0.08);
      background: rgba(255, 255, 255, 0.68);
    }}
    .chip .stat-value {{
      font-size: 1rem;
    }}
    .confidence-list {{
      display: grid;
      gap: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(84px, 112px) 1fr auto;
      gap: 12px;
      align-items: center;
    }}
    .bar-label {{
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .bar-track {{
      height: 13px;
      border-radius: 999px;
      background: rgba(31, 30, 26, 0.08);
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      width: 0%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent-2), var(--accent), var(--accent-3));
    }}
    .status {{
      min-height: 24px;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .tiny {{
      font-size: 0.85rem;
      color: var(--muted);
    }}
    code {{
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 0.92em;
      background: rgba(31, 30, 26, 0.06);
      padding: 2px 6px;
      border-radius: 8px;
    }}
    input[type="file"] {{
      display: none;
    }}
    @media (max-width: 900px) {{
      .workspace {{ grid-template-columns: 1fr; }}
      .sample-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .shell {{ width: min(100vw - 20px, 1180px); margin: 10px auto 20px; }}
      .hero, .panel {{ border-radius: 24px; }}
    }}
    @media (max-width: 560px) {{
      .sample-grid {{ grid-template-columns: 1fr; }}
      .headline-row {{ flex-direction: column; align-items: start; }}
      .bar-row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Web4 Frontend</div>
      <h1>Upload a photo. Let the contract decide if it is a hotdog.</h1>
      <p class="lead">
        This page is served directly from the NEAR contract through <code>web4_get</code>. The model is a quantized
        500k-parameter CNN running fully on-chain. Images are center-cropped and downsampled to <code>{input_width}×{input_height} RGB</code>
        in the browser before the contract runs inference.
      </p>
      <div class="hero-grid">
        <div class="stat">
          <div class="stat-label">Contract</div>
          <div class="stat-value">{contract_id}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Measured Tx Gas</div>
          <div class="stat-value">~264.865 Tgas</div>
        </div>
        <div class="stat">
          <div class="stat-label">Model Size</div>
          <div class="stat-value">499,994 params</div>
        </div>
        <div class="stat">
          <div class="stat-label">Input</div>
          <div class="stat-value">{input_width}×{input_height} RGB</div>
        </div>
      </div>
    </section>

    <section class="workspace">
      <div class="panel">
        <h2>Input</h2>
        <p>
          Try one of the embedded evaluation samples, or upload your own image. The browser only does the resize step;
          the classification itself comes from the contract.
        </p>
        <div class="preview-stack">
          <div class="preview-frame">
            <canvas id="preview" class="preview" width="{input_width}" height="{input_height}" aria-label="{input_width} by {input_height} image preview"></canvas>
            <div class="caption-row">
              <span id="preview-label">Awaiting image</span>
              <span class="tiny">center crop + downsample</span>
            </div>
          </div>
          <div class="dropzone">
            <strong>Bring your own image</strong>
            <span class="tiny">PNG, JPEG, WebP, or HEIC if the browser can decode it.</span>
            <div class="controls">
              <label class="file-button primary" for="upload-input">Choose image</label>
              <button id="predict-button" class="secondary" type="button">Run current pixels</button>
              <button id="reset-button" class="ghost" type="button">Reset preview</button>
              <input id="upload-input" type="file" accept="image/*">
            </div>
          </div>
        </div>

        <div class="caption-row" style="margin-top: 18px;">
          <strong>Embedded samples</strong>
          <span id="network-badge" class="stat-label"></span>
        </div>
        <div class="sample-grid" id="sample-grid"></div>
      </div>

      <div class="panel">
        <h2>Result</h2>
        <p id="model-summary">Loading model metadata...</p>
        <div class="result-card">
          <div class="headline-row">
            <div class="verdict">
              <div class="stat-label">Prediction</div>
              <div class="verdict-title" id="verdict-title">No image yet</div>
              <div id="verdict-badge" class="verdict-badge">
                <span>Idle</span>
              </div>
            </div>
            <div class="chip">
              <div class="stat-label">RPC</div>
              <div class="stat-value"><code id="rpc-url">loading</code></div>
            </div>
          </div>
          <div class="summary-grid">
            <div class="chip">
              <div class="stat-label">Source</div>
              <div class="stat-value" id="source-name">none</div>
            </div>
            <div class="chip">
              <div class="stat-label">Input Prep</div>
              <div class="stat-value">center crop → {input_width}×{input_height}</div>
            </div>
            <div class="chip">
              <div class="stat-label">Execution</div>
              <div class="stat-value">contract view call</div>
            </div>
          </div>
          <div class="confidence-list" id="confidence-list"></div>
          <div class="status" id="status"></div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const contractId = {contract_id:?};
    const inputWidth = {input_width};
    const inputHeight = {input_height};
    const inputChannels = {input_channels};
    const inputSize = inputWidth * inputHeight * inputChannels;
    const isTestnet = contractId.endsWith('.testnet');
    const rpcUrl = isTestnet ? 'https://rpc.testnet.near.org' : 'https://rpc.mainnet.near.org';
    const state = {{
      labels: ['hotdog', 'not hotdog'],
      currentPixels: new Uint8Array(inputSize),
      sourceName: 'none',
      activeSampleButton: null,
    }};

    const previewCanvas = document.getElementById('preview');
    const previewCtx = previewCanvas.getContext('2d', {{ alpha: false }});
    const previewLabelEl = document.getElementById('preview-label');
    const statusEl = document.getElementById('status');
    const verdictTitleEl = document.getElementById('verdict-title');
    const verdictBadgeEl = document.getElementById('verdict-badge');
    const sourceNameEl = document.getElementById('source-name');
    const modelSummaryEl = document.getElementById('model-summary');
    const confidenceList = document.getElementById('confidence-list');
    const sampleGrid = document.getElementById('sample-grid');
    const uploadInput = document.getElementById('upload-input');
    const predictButton = document.getElementById('predict-button');
    const resetButton = document.getElementById('reset-button');

    document.getElementById('rpc-url').textContent = rpcUrl;
    document.getElementById('network-badge').textContent = isTestnet ? 'testnet' : 'mainnet';

    function prettyLabel(value) {{
      return String(value).replaceAll('_', ' ');
    }}

    function setStatus(message) {{
      statusEl.textContent = message;
    }}

    function setBusy(isBusy) {{
      predictButton.disabled = isBusy;
      resetButton.disabled = isBusy;
      uploadInput.disabled = isBusy;
    }}

    function setActiveSample(button) {{
      if (state.activeSampleButton) {{
        state.activeSampleButton.classList.remove('active');
      }}
      state.activeSampleButton = button;
      if (button) {{
        button.classList.add('active');
      }}
    }}

    function clearPreview() {{
      previewCtx.fillStyle = '#f7f3ea';
      previewCtx.fillRect(0, 0, inputWidth, inputHeight);
    }}

    function drawPixels(pixels) {{
      const image = previewCtx.createImageData(inputWidth, inputHeight);
      for (let i = 0; i < inputWidth * inputHeight; i += 1) {{
        const offset = i * 4;
        const rgbOffset = i * inputChannels;
        image.data[offset] = pixels[rgbOffset];
        image.data[offset + 1] = pixels[rgbOffset + 1];
        image.data[offset + 2] = pixels[rgbOffset + 2];
        image.data[offset + 3] = 255;
      }}
      previewCtx.putImageData(image, 0, 0);
    }}

    function encodeArgs(args) {{
      const bytes = new TextEncoder().encode(JSON.stringify(args));
      let binary = '';
      for (const byte of bytes) {{
        binary += String.fromCharCode(byte);
      }}
      return btoa(binary);
    }}

    async function viewCall(methodName, args) {{
      const response = await fetch(rpcUrl, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          jsonrpc: '2.0',
          id: 'web4-hotdog',
          method: 'query',
          params: {{
            request_type: 'call_function',
            finality: 'final',
            account_id: contractId,
            method_name: methodName,
            args_base64: encodeArgs(args),
          }},
        }}),
      }});

      const json = await response.json();
      if (json.error) {{
        throw new Error(json.error.data || json.error.message || 'RPC error');
      }}

      const bytes = new Uint8Array(json.result.result);
      return JSON.parse(new TextDecoder().decode(bytes));
    }}

    function renderConfidence(logits) {{
      confidenceList.innerHTML = '';
      const max = Math.max(...logits.map((value) => Math.max(0, value)), 1);
      logits.forEach((value, index) => {{
        const row = document.createElement('div');
        row.className = 'bar-row';

        const label = document.createElement('div');
        label.className = 'bar-label';
        label.textContent = prettyLabel(state.labels[index] || ('class ' + index));

        const track = document.createElement('div');
        track.className = 'bar-track';
        const fill = document.createElement('div');
        fill.className = 'bar-fill';
        fill.style.width = Math.max(6, (Math.max(0, value) / max) * 100) + '%';
        track.appendChild(fill);

        const amount = document.createElement('div');
        amount.textContent = value;

        row.append(label, track, amount);
        confidenceList.appendChild(row);
      }});
    }}

    function renderPrediction(prediction, sourceName) {{
      const label = prettyLabel(prediction.predicted_label || state.labels[prediction.predicted_index] || 'unknown');
      verdictTitleEl.textContent = label;
      verdictBadgeEl.className = 'verdict-badge ' + label.replaceAll(' ', '-');
      verdictBadgeEl.textContent = 'class ' + prediction.predicted_index + ' · ' + label;
      sourceNameEl.textContent = sourceName;
      renderConfidence(prediction.logits);
    }}

    async function loadModelInfo() {{
      const info = await viewCall('model_info', {{}});
      state.labels = info.labels.map(prettyLabel);
      modelSummaryEl.textContent =
        info.description +
        ' Conv stack: ' + info.conv1_channels + '/' + info.conv2_channels + '/' + info.conv3_channels +
        ', MLP head: ' + info.mlp_hidden_size +
        ', samples: ' + info.sample_count + '.';
    }}

    async function predictPixels(pixels, sourceName) {{
      setBusy(true);
      setStatus('Running contract inference...');
      try {{
        const prediction = await viewCall('predict_pixels', {{ pixels: Array.from(pixels) }});
        state.currentPixels.set(pixels);
        state.sourceName = sourceName;
        drawPixels(state.currentPixels);
        previewLabelEl.textContent = sourceName;
        renderPrediction(prediction, sourceName);
        setStatus('Inference complete.');
      }} catch (error) {{
        console.error(error);
        setStatus('Inference failed: ' + error.message);
      }} finally {{
        setBusy(false);
      }}
    }}

    async function activateSample(sample, button) {{
      setBusy(true);
      setStatus('Loading embedded sample ' + sample.sample_index + '...');
      try {{
        const pixels = await viewCall('sample_pixels', {{ sample_index: sample.sample_index }});
        setActiveSample(button);
        await predictPixels(new Uint8Array(pixels), 'sample ' + sample.sample_index + ' · ' + prettyLabel(state.labels[sample.expected_index]));
      }} finally {{
        setBusy(false);
      }}
    }}

    async function loadSampleGrid() {{
      const samples = await viewCall('sample_predictions', {{}});
      sampleGrid.innerHTML = '';
      for (const sample of samples) {{
        const pixels = await viewCall('sample_pixels', {{ sample_index: sample.sample_index }});
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sample-card';

        const thumb = document.createElement('canvas');
        thumb.width = inputWidth;
        thumb.height = inputHeight;
        drawPixelsOnCanvas(thumb, pixels);

        const meta = document.createElement('div');
        meta.className = 'sample-meta';

        const title = document.createElement('div');
        title.className = 'sample-title';
        title.textContent = 'Sample ' + sample.sample_index;

        const expected = document.createElement('div');
        expected.className = 'sample-note';
        expected.textContent = 'expected: ' + prettyLabel(state.labels[sample.expected_index]);

        const predicted = document.createElement('div');
        predicted.className = 'sample-note';
        predicted.textContent = 'predicted: ' + prettyLabel(sample.predicted_label);

        meta.append(title, expected, predicted);
        button.append(thumb, meta);
        button.addEventListener('click', () => activateSample(sample, button));
        sampleGrid.appendChild(button);
      }}
    }}

    function drawPixelsOnCanvas(canvas, pixels) {{
      const ctx = canvas.getContext('2d', {{ alpha: false }});
      const image = ctx.createImageData(inputWidth, inputHeight);
      for (let i = 0; i < inputWidth * inputHeight; i += 1) {{
        const offset = i * 4;
        const rgbOffset = i * inputChannels;
        image.data[offset] = pixels[rgbOffset];
        image.data[offset + 1] = pixels[rgbOffset + 1];
        image.data[offset + 2] = pixels[rgbOffset + 2];
        image.data[offset + 3] = 255;
      }}
      ctx.putImageData(image, 0, 0);
    }}

    function loadImage(url) {{
      return new Promise((resolve, reject) => {{
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('Could not decode image'));
        image.src = url;
      }});
    }}

    async function imageFileToPixels(file) {{
      const objectUrl = URL.createObjectURL(file);
      try {{
        const image = await loadImage(objectUrl);
        const cropSize = Math.min(image.width, image.height);
        const sourceX = (image.width - cropSize) / 2;
        const sourceY = (image.height - cropSize) / 2;

        const canvas = document.createElement('canvas');
        canvas.width = inputWidth;
        canvas.height = inputHeight;
        const ctx = canvas.getContext('2d', {{ willReadFrequently: true }});
        ctx.drawImage(image, sourceX, sourceY, cropSize, cropSize, 0, 0, inputWidth, inputHeight);

        const data = ctx.getImageData(0, 0, inputWidth, inputHeight).data;
        const pixels = new Uint8Array(inputSize);
        for (let i = 0; i < inputWidth * inputHeight; i += 1) {{
          const imageOffset = i * 4;
          const pixelOffset = i * inputChannels;
          pixels[pixelOffset] = data[imageOffset];
          pixels[pixelOffset + 1] = data[imageOffset + 1];
          pixels[pixelOffset + 2] = data[imageOffset + 2];
        }}
        return pixels;
      }} finally {{
        URL.revokeObjectURL(objectUrl);
      }}
    }}

    uploadInput.addEventListener('change', async (event) => {{
      const file = event.target.files && event.target.files[0];
      if (!file) {{
        return;
      }}
      setActiveSample(null);
      setStatus('Preparing upload...');
      try {{
        const pixels = await imageFileToPixels(file);
        await predictPixels(pixels, file.name + ' · ' + inputWidth + '×' + inputHeight);
      }} catch (error) {{
        console.error(error);
        setStatus('Upload failed: ' + error.message);
      }} finally {{
        uploadInput.value = '';
      }}
    }});

    predictButton.addEventListener('click', async () => {{
      if (!state.currentPixels.some((value) => value !== 0)) {{
        setStatus('Load a sample or upload an image first.');
        return;
      }}
      await predictPixels(state.currentPixels, state.sourceName || 'current preview');
    }});

    resetButton.addEventListener('click', () => {{
      state.currentPixels.fill(0);
      state.sourceName = 'none';
      setActiveSample(null);
      clearPreview();
      previewLabelEl.textContent = 'Awaiting image';
      verdictTitleEl.textContent = 'No image yet';
      verdictBadgeEl.className = 'verdict-badge';
      verdictBadgeEl.textContent = 'Idle';
      sourceNameEl.textContent = 'none';
      confidenceList.innerHTML = '';
      setStatus('Preview reset.');
    }});

    clearPreview();
    loadModelInfo()
      .then(loadSampleGrid)
      .then(async () => {{
        const firstSampleButton = sampleGrid.querySelector('button');
        if (firstSampleButton) {{
          firstSampleButton.click();
        }}
      }})
      .catch((error) => {{
        console.error(error);
        setStatus('Failed to initialize page: ' + error.message);
      }});
  </script>
</body>
</html>"##
    ,
        input_width = model_data::INPUT_WIDTH,
        input_height = model_data::INPUT_HEIGHT,
        input_channels = model_data::INPUT_CHANNELS,
    )
}

fn conv2d_same_stride2_u8(
    input: &[u8],
    width: usize,
    height: usize,
    in_channels: usize,
    weights: &[i16],
    biases: &[i32],
    out_channels: usize,
    input_divisor: i64,
) -> Vec<i32> {
    let out_width = width / 2;
    let out_height = height / 2;
    let mut output = vec![0; out_width * out_height * out_channels];
    for y in 0..out_height {
        let in_y_center = y * 2;
        for x in 0..out_width {
            let in_x_center = x * 2;
            for out_channel in 0..out_channels {
                let mut total = biases[out_channel] as i64;
                for in_channel in 0..in_channels {
                    for ky in 0..3 {
                        let iy = in_y_center as isize + ky as isize - 1;
                        if iy < 0 || iy >= height as isize {
                            continue;
                        }
                        for kx in 0..3 {
                            let ix = in_x_center as isize + kx as isize - 1;
                            if ix < 0 || ix >= width as isize {
                                continue;
                            }
                            let input_index =
                                ((iy as usize * width + ix as usize) * in_channels) + in_channel;
                            let weight_index =
                                (((out_channel * in_channels + in_channel) * 3 + ky) * 3) + kx;
                            total += (weights[weight_index] as i64 * input[input_index] as i64)
                                / input_divisor;
                        }
                    }
                }
                output[((y * out_width + x) * out_channels) + out_channel] = clamp_to_i32(total);
            }
        }
    }
    output
}

fn conv2d_same_i32(
    input: &[i32],
    width: usize,
    height: usize,
    in_channels: usize,
    weights: &[i16],
    biases: &[i32],
    out_channels: usize,
    input_divisor: i64,
) -> Vec<i32> {
    let mut output = vec![0; width * height * out_channels];
    for y in 0..height {
        for x in 0..width {
            for out_channel in 0..out_channels {
                let mut total = biases[out_channel] as i64;
                for in_channel in 0..in_channels {
                    for ky in 0..3 {
                        let iy = y as isize + ky as isize - 1;
                        if iy < 0 || iy >= height as isize {
                            continue;
                        }
                        for kx in 0..3 {
                            let ix = x as isize + kx as isize - 1;
                            if ix < 0 || ix >= width as isize {
                                continue;
                            }
                            let input_index =
                                ((iy as usize * width + ix as usize) * in_channels) + in_channel;
                            let weight_index =
                                (((out_channel * in_channels + in_channel) * 3 + ky) * 3) + kx;
                            total += (weights[weight_index] as i64 * input[input_index] as i64)
                                / input_divisor;
                        }
                    }
                }
                output[((y * width + x) * out_channels) + out_channel] = clamp_to_i32(total);
            }
        }
    }
    output
}

fn relu_in_place(mut values: Vec<i32>) -> Vec<i32> {
    for value in &mut values {
        *value = (*value).max(0);
    }
    values
}

fn max_pool2x2(input: &[i32], width: usize, height: usize, channels: usize) -> Vec<i32> {
    let out_width = width / 2;
    let out_height = height / 2;
    let mut output = vec![0; out_width * out_height * channels];
    for y in 0..out_height {
        for x in 0..out_width {
            for channel in 0..channels {
                let mut max_value = i32::MIN;
                for py in 0..2 {
                    for px in 0..2 {
                        let in_y = y * 2 + py;
                        let in_x = x * 2 + px;
                        let index = ((in_y * width + in_x) * channels) + channel;
                        max_value = max_value.max(input[index]);
                    }
                }
                output[((y * out_width + x) * channels) + channel] = max_value;
            }
        }
    }
    output
}

fn global_average_pool(input: &[i32], width: usize, height: usize, channels: usize) -> Vec<i32> {
    let divisor = (width * height) as i64;
    (0..channels)
        .map(|channel| {
            let mut total = 0i64;
            for y in 0..height {
                for x in 0..width {
                    total += input[((y * width + x) * channels) + channel] as i64;
                }
            }
            clamp_to_i32(total / divisor)
        })
        .collect()
}

fn linear(
    input: &[i32],
    weights: &[i16],
    biases: &[i32],
    input_size: usize,
    output_size: usize,
    input_divisor: i64,
) -> Vec<i32> {
    (0..output_size)
        .map(|output_index| {
            let mut total = biases[output_index] as i64;
            for input_index in 0..input_size {
                total += (weights[output_index * input_size + input_index] as i64
                    * input[input_index] as i64)
                    / input_divisor;
            }
            clamp_to_i32(total)
        })
        .collect()
}

fn argmax(values: &[i32]) -> usize {
    values
        .iter()
        .enumerate()
        .max_by_key(|(_, value)| *value)
        .map(|(idx, _)| idx)
        .unwrap_or(0)
}

fn clamp_to_i32(value: i64) -> i32 {
    value.clamp(i32::MIN as i64, i32::MAX as i64) as i32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn predicts_embedded_samples_correctly() {
        let contract = HotdogCnnContract::new();

        for sample in contract.sample_predictions() {
            assert_eq!(
                sample.predicted_index, sample.expected_index,
                "sample index {}",
                sample.sample_index
            );
        }
    }

    #[test]
    fn predicts_uploaded_sample_pixels_correctly() {
        let contract = HotdogCnnContract::new();

        for (sample_index, expected_index) in model_data::SAMPLE_LABELS.iter().enumerate() {
            let pixels = contract.sample_pixels(sample_index as u8);
            let prediction = contract.predict_pixels(pixels);
            assert_eq!(
                prediction.predicted_index, *expected_index,
                "sample index {sample_index}"
            );
        }
    }

    #[test]
    fn exposes_expected_model_shape() {
        let contract = HotdogCnnContract::new();
        let info = contract.model_info();

        assert_eq!(info.input_width, model_data::INPUT_WIDTH);
        assert_eq!(info.input_height, model_data::INPUT_HEIGHT);
        assert_eq!(info.input_channels, model_data::INPUT_CHANNELS);
        assert_eq!(info.conv3_channels, model_data::CONV3_OUT_CHANNELS);
        assert_eq!(info.output_size, 2);
        assert_eq!(
            info.labels,
            vec!["hotdog".to_string(), "not_hotdog".to_string()]
        );
    }
}
