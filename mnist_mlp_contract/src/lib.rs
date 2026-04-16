mod model_data;

use std::collections::HashMap;

use near_sdk::env;
use near_sdk::json_types::Base64VecU8;
use near_sdk::serde::{Deserialize, Serialize};
use near_sdk::{near, PanicOnDefault};

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct ModelInfo {
    pub input_size: usize,
    pub hidden_size: usize,
    pub output_size: usize,
    pub input_scale: i32,
    pub weight_scale: i32,
    pub description: String,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct DigitPrediction {
    pub logits: Vec<i32>,
    pub predicted_digit: u8,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct SamplePrediction {
    pub sample_digit: u8,
    pub predicted_digit: u8,
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
pub struct MnistMlpContract {
    initialized: bool,
}

#[near]
impl MnistMlpContract {
    #[init]
    pub fn new() -> Self {
        Self { initialized: true }
    }

    pub fn model_info(&self) -> ModelInfo {
        ModelInfo {
            input_size: model_data::INPUT_SIZE,
            hidden_size: model_data::HIDDEN_SIZE,
            output_size: model_data::OUTPUT_SIZE,
            input_scale: model_data::INPUT_SCALE,
            weight_scale: model_data::WEIGHT_SCALE,
            description: "Quantized 784 -> 24 -> 10 MNIST MLP. Inputs are raw grayscale pixels in the 0..255 range and inference runs fully inside the contract.".to_string(),
        }
    }

    pub fn predict_pixels(&self, pixels: Vec<u8>) -> DigitPrediction {
        assert_eq!(
            pixels.len(),
            model_data::INPUT_SIZE,
            "expected {} pixels, got {}",
            model_data::INPUT_SIZE,
            pixels.len()
        );

        let hidden = run_hidden_layer(&pixels);
        let logits = run_output_layer(&hidden);
        let predicted_digit = argmax(&logits) as u8;

        DigitPrediction {
            logits,
            predicted_digit,
        }
    }

    pub fn predict_sample(&self, digit: u8) -> DigitPrediction {
        self.predict_pixels(self.sample_pixels(digit))
    }

    pub fn sample_pixels(&self, digit: u8) -> Vec<u8> {
        let index = sample_index(digit);
        model_data::SAMPLE_IMAGES[index].to_vec()
    }

    pub fn sample_predictions(&self) -> Vec<SamplePrediction> {
        model_data::SAMPLE_LABELS
            .iter()
            .enumerate()
            .map(|(idx, label)| SamplePrediction {
                sample_digit: *label,
                predicted_digit: self
                    .predict_pixels(model_data::SAMPLE_IMAGES[idx].to_vec())
                    .predicted_digit,
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

fn run_hidden_layer(pixels: &[u8]) -> Vec<i32> {
    model_data::HIDDEN_WEIGHTS
        .iter()
        .zip(model_data::HIDDEN_BIASES.iter())
        .map(|(weights, bias)| {
            let sum =
                weights
                    .iter()
                    .zip(pixels.iter())
                    .fold(*bias as i64, |acc, (weight, pixel)| {
                        acc + ((*weight as i64) * (*pixel as i64) / model_data::INPUT_SCALE as i64)
                    });
            clamp_to_i32(sum).max(0)
        })
        .collect()
}

fn sample_index(digit: u8) -> usize {
    let index = digit as usize;
    assert!(
        index < model_data::SAMPLE_IMAGES.len(),
        "sample digit must be in 0..={}",
        model_data::SAMPLE_IMAGES.len() - 1
    );
    index
}

fn render_web4_page(contract_id: &str) -> String {
    format!(
        r##"<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>On-Chain MNIST on NEAR</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: rgba(255, 252, 245, 0.88);
      --ink: #182028;
      --muted: #667085;
      --accent: #e4572e;
      --accent-2: #1f7a8c;
      --line: rgba(24, 32, 40, 0.12);
      --shadow: 0 18px 48px rgba(24, 32, 40, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(31, 122, 140, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(228, 87, 46, 0.18), transparent 24%),
        linear-gradient(180deg, #f8f4ec 0%, #ece3d5 100%);
    }}
    .shell {{
      width: min(1120px, calc(100vw - 32px));
      margin: 32px auto;
      display: grid;
      gap: 20px;
    }}
    .hero, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .hero {{
      padding: 28px;
      display: grid;
      gap: 14px;
    }}
    .eyebrow {{
      letter-spacing: 0.16em;
      text-transform: uppercase;
      font-size: 12px;
      color: var(--accent-2);
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 6vw, 4.6rem);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .lead {{
      max-width: 760px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.6;
      margin: 0;
    }}
    .hero-grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .stat {{
      padding: 16px 18px;
      border-radius: 18px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(24, 32, 40, 0.08);
    }}
    .stat-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
    }}
    .stat-value {{
      margin-top: 8px;
      font-size: 1.25rem;
      font-weight: 700;
    }}
    .workspace {{
      display: grid;
      gap: 20px;
      grid-template-columns: minmax(280px, 420px) minmax(320px, 1fr);
    }}
    .panel {{
      padding: 22px;
    }}
    .panel h2 {{
      margin: 0 0 10px;
      font-size: 1.35rem;
      letter-spacing: -0.03em;
    }}
    .panel p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .canvas-wrap {{
      margin-top: 18px;
      display: grid;
      gap: 14px;
      justify-items: center;
    }}
    canvas {{
      width: min(100%, 360px);
      aspect-ratio: 1;
      border-radius: 20px;
      border: 1px solid rgba(24, 32, 40, 0.14);
      background: #fff;
      image-rendering: pixelated;
      box-shadow: inset 0 0 0 1px rgba(24, 32, 40, 0.04);
      touch-action: none;
    }}
    .toolbar, .sample-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      font: inherit;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease, box-shadow 120ms ease;
    }}
    button:hover {{ transform: translateY(-1px); }}
    button:disabled {{ opacity: 0.55; cursor: wait; transform: none; }}
    .primary {{
      background: linear-gradient(135deg, var(--accent), #ff7a45);
      color: #fff;
      box-shadow: 0 12px 24px rgba(228, 87, 46, 0.25);
    }}
    .secondary {{
      background: rgba(31, 122, 140, 0.1);
      color: var(--accent-2);
    }}
    .ghost {{
      background: rgba(24, 32, 40, 0.06);
      color: var(--ink);
    }}
    .sample {{
      min-width: 44px;
      text-align: center;
      padding-inline: 14px;
    }}
    .row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 18px 0 12px;
    }}
    .result-digit {{
      display: inline-grid;
      place-items: center;
      width: 92px;
      height: 92px;
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(31, 122, 140, 0.12), rgba(228, 87, 46, 0.16));
      font-size: 3rem;
      font-weight: 800;
      letter-spacing: -0.06em;
    }}
    .confidence-list {{
      margin-top: 18px;
      display: grid;
      gap: 10px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 24px 1fr auto;
      gap: 12px;
      align-items: center;
    }}
    .bar-track {{
      height: 12px;
      border-radius: 999px;
      background: rgba(24, 32, 40, 0.08);
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent-2), var(--accent));
      width: 0%;
    }}
    .status {{
      margin-top: 18px;
      min-height: 24px;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    code {{
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 0.92em;
      background: rgba(24, 32, 40, 0.06);
      padding: 2px 6px;
      border-radius: 8px;
    }}
    @media (max-width: 860px) {{
      .workspace {{ grid-template-columns: 1fr; }}
      .shell {{ width: min(100vw - 20px, 1120px); margin: 10px auto 20px; }}
      .hero, .panel {{ border-radius: 20px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow">Web4 Frontend</div>
      <h1>Inspect MNIST samples on NEAR.</h1>
      <p class="lead">
        This page is served by the same contract that stores the MNIST model.
        For now the frontend focuses on the embedded demo digits that the contract
        classifies reliably, so you can inspect outputs without the noisy drawing path.
      </p>
      <div class="hero-grid">
        <div class="stat">
          <div class="stat-label">Contract</div>
          <div class="stat-value" id="contract-id">{contract_id}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Execution Path</div>
          <div class="stat-value">On-chain view inference</div>
        </div>
        <div class="stat">
          <div class="stat-label">Measured Tx Gas</div>
          <div class="stat-value">~2.273 Tgas</div>
        </div>
      </div>
    </section>

    <section class="workspace">
      <div class="panel">
        <h2>Samples</h2>
        <p>Pick one of the embedded digits below. The contract returns both the sample pixels and the inference result.</p>
        <div class="canvas-wrap">
          <canvas id="pad" width="28" height="28" aria-label="28 by 28 sample preview"></canvas>
          <!--
          <div class="toolbar">
            <button id="predict" class="primary">Predict</button>
            <button id="clear" class="ghost">Clear</button>
            <button id="invert" class="ghost">Invert</button>
          </div>
          -->
        </div>
        <div class="row">
          <strong>Embedded samples</strong>
          <span id="network-badge" class="stat-label"></span>
        </div>
        <div class="sample-grid" id="sample-grid"></div>
      </div>

      <div class="panel">
        <h2>Output</h2>
        <p id="model-summary">Loading model metadata...</p>
        <div class="row">
          <div>
            <div class="stat-label">Predicted digit</div>
            <div class="result-digit" id="result-digit">?</div>
          </div>
          <div>
            <div class="stat-label">RPC</div>
            <div id="rpc-url"><code>loading</code></div>
          </div>
        </div>
        <div class="confidence-list" id="confidence-list"></div>
        <div class="status" id="status"></div>
      </div>
    </section>
  </main>

  <script>
    const contractId = {contract_id:?};
    const isTestnet = contractId.endsWith('.testnet');
    const rpcUrl = isTestnet ? 'https://rpc.testnet.near.org' : 'https://rpc.mainnet.near.org';
    const pixels = new Uint8Array(28 * 28);
    const canvas = document.getElementById('pad');
    const ctx = canvas.getContext('2d', {{ alpha: false }});
    const statusEl = document.getElementById('status');
    const resultDigitEl = document.getElementById('result-digit');
    const modelSummaryEl = document.getElementById('model-summary');
    // const predictButton = document.getElementById('predict');
    const sampleGrid = document.getElementById('sample-grid');
    const confidenceList = document.getElementById('confidence-list');

    document.getElementById('rpc-url').innerHTML = '<code>' + rpcUrl + '</code>';
    document.getElementById('network-badge').textContent = isTestnet ? 'testnet' : 'mainnet';

    for (let digit = 0; digit < 10; digit += 1) {{
      const button = document.createElement('button');
      button.className = 'secondary sample';
      button.textContent = digit;
      button.addEventListener('click', () => loadSample(digit));
      sampleGrid.appendChild(button);
    }}

    function setStatus(message) {{
      statusEl.textContent = message;
    }}

    function renderPixels() {{
      const image = ctx.createImageData(28, 28);
      for (let i = 0; i < pixels.length; i += 1) {{
        const value = 255 - pixels[i];
        const offset = i * 4;
        image.data[offset] = value;
        image.data[offset + 1] = value;
        image.data[offset + 2] = value;
        image.data[offset + 3] = 255;
      }}
      ctx.putImageData(image, 0, 0);
    }}

    /*
    function writeAt(event) {{
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - rect.left) / rect.width) * 28);
      const y = Math.floor(((event.clientY - rect.top) / rect.height) * 28);
      if (x < 0 || y < 0 || x >= 28 || y >= 28) return;
      const index = y * 28 + x;
      pixels[index] = 255;
      for (let dy = -1; dy <= 1; dy += 1) {{
        for (let dx = -1; dx <= 1; dx += 1) {{
          const nx = x + dx;
          const ny = y + dy;
          if (nx >= 0 && ny >= 0 && nx < 28 && ny < 28) {{
            pixels[ny * 28 + nx] = Math.max(pixels[ny * 28 + nx], 180);
          }}
        }}
      }}
      renderPixels();
    }}

    let drawing = false;
    canvas.addEventListener('pointerdown', (event) => {{
      drawing = true;
      canvas.setPointerCapture(event.pointerId);
      writeAt(event);
    }});
    canvas.addEventListener('pointermove', (event) => {{
      if (drawing) writeAt(event);
    }});
    canvas.addEventListener('pointerup', () => {{ drawing = false; }});
    canvas.addEventListener('pointerleave', () => {{ drawing = false; }});

    document.getElementById('clear').addEventListener('click', () => {{
      pixels.fill(0);
      renderPixels();
      resultDigitEl.textContent = '?';
      setStatus('Canvas cleared.');
    }});

    document.getElementById('invert').addEventListener('click', () => {{
      for (let i = 0; i < pixels.length; i += 1) {{
        pixels[i] = 255 - pixels[i];
      }}
      renderPixels();
      setStatus('Pixels inverted.');
    }});
    */

    function encodeArgs(args) {{
      const bytes = new TextEncoder().encode(JSON.stringify(args));
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      return btoa(binary);
    }}

    async function viewCall(methodName, args) {{
      const response = await fetch(rpcUrl, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          jsonrpc: '2.0',
          id: 'web4-mnist',
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

    function renderLogits(logits) {{
      confidenceList.innerHTML = '';
      const max = Math.max(...logits.map((value) => Math.max(0, value)), 1);
      logits.forEach((value, digit) => {{
        const row = document.createElement('div');
        row.className = 'bar-row';
        const label = document.createElement('strong');
        label.textContent = digit;
        const track = document.createElement('div');
        track.className = 'bar-track';
        const fill = document.createElement('div');
        fill.className = 'bar-fill';
        fill.style.width = Math.max(4, (Math.max(0, value) / max) * 100) + '%';
        track.appendChild(fill);
        const amount = document.createElement('span');
        amount.textContent = value;
        row.append(label, track, amount);
        confidenceList.appendChild(row);
      }});
    }}

    async function loadModelInfo() {{
      const info = await viewCall('model_info', {{}});
      modelSummaryEl.textContent = info.description + ' Hidden: ' + info.hidden_size + ', output: ' + info.output_size + ', input scale: ' + info.input_scale + ', weight scale: ' + info.weight_scale + '.';
    }}

    async function loadSample(digit) {{
      setStatus('Loading embedded sample ' + digit + '...');
      const sample = await viewCall('sample_pixels', {{ digit }});
      pixels.set(sample);
      renderPixels();
      const prediction = await viewCall('predict_sample', {{ digit }});
      resultDigitEl.textContent = prediction.predicted_digit;
      renderLogits(prediction.logits);
      setStatus('Loaded embedded sample ' + digit + ' and ran inference.');
    }}

    /*
    async function predictCurrent() {{
      predictButton.disabled = true;
      setStatus('Running on-chain inference...');
      try {{
        const prediction = await viewCall('predict_pixels', {{ pixels: Array.from(pixels) }});
        resultDigitEl.textContent = prediction.predicted_digit;
        renderLogits(prediction.logits);
        setStatus('Predicted digit ' + prediction.predicted_digit + ' from 784 uploaded pixels.');
      }} catch (error) {{
        console.error(error);
        setStatus('Prediction failed: ' + error.message);
      }} finally {{
        predictButton.disabled = false;
      }}
    }}

    predictButton.addEventListener('click', predictCurrent);
    */

    renderPixels();
    loadModelInfo()
      .then(() => loadSample(7))
      .catch((error) => {{
        console.error(error);
        setStatus('Failed to load model metadata: ' + error.message);
      }});
  </script>
</body>
</html>"##
    )
}

fn run_output_layer(hidden: &[i32]) -> Vec<i32> {
    model_data::OUTPUT_WEIGHTS
        .iter()
        .zip(model_data::OUTPUT_BIASES.iter())
        .map(|(weights, bias)| {
            let sum =
                weights
                    .iter()
                    .zip(hidden.iter())
                    .fold(*bias as i64, |acc, (weight, value)| {
                        acc + ((*weight as i64) * (*value as i64) / model_data::WEIGHT_SCALE as i64)
                    });
            clamp_to_i32(sum)
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
    fn predicts_all_embedded_samples_correctly() {
        let contract = MnistMlpContract::new();

        for label in model_data::SAMPLE_LABELS {
            let prediction = contract.predict_sample(label);
            assert_eq!(prediction.predicted_digit, label, "sample digit {label}");
        }
    }

    #[test]
    fn predicts_uploaded_pixels_correctly() {
        let contract = MnistMlpContract::new();

        for label in model_data::SAMPLE_LABELS {
            let pixels = contract.sample_pixels(label);
            let prediction = contract.predict_pixels(pixels);
            assert_eq!(
                prediction.predicted_digit, label,
                "uploaded sample digit {label}"
            );
        }
    }

    #[test]
    fn exposes_expected_model_shape() {
        let contract = MnistMlpContract::new();
        let info = contract.model_info();

        assert_eq!(info.input_size, 784);
        assert_eq!(info.hidden_size, 24);
        assert_eq!(info.output_size, 10);
        assert_eq!(info.input_scale, 255);
        assert_eq!(info.weight_scale, 256);
    }

    #[test]
    fn serves_web4_html() {
        let contract = MnistMlpContract::new();
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
                assert!(html.contains("Inspect MNIST samples on NEAR."));
                assert!(html.contains("predict_sample"));
            }
            Web4Response::Status { status } => panic!("unexpected status response: {status}"),
        }
    }
}
