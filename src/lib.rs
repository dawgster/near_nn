use near_sdk::borsh::{BorshDeserialize, BorshSerialize};
use near_sdk::serde::{Deserialize, Serialize};
use near_sdk::{near, PanicOnDefault};

#[derive(BorshDeserialize, BorshSerialize, Serialize, Deserialize, Clone)]
#[serde(crate = "near_sdk::serde")]
pub struct DenseLayer {
    pub weights: Vec<Vec<i32>>,
    pub biases: Vec<i32>,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct ModelInfo {
    pub input_size: usize,
    pub hidden_size: usize,
    pub output_size: usize,
    pub scale: i32,
    pub description: String,
}

#[derive(Serialize, Deserialize)]
#[serde(crate = "near_sdk::serde")]
pub struct Prediction {
    pub hidden_layer: Vec<i32>,
    pub output_layer: Vec<i32>,
    pub predicted_class: bool,
}

#[derive(PanicOnDefault)]
#[near(contract_state)]
pub struct NeuralNetworkContract {
    scale: i32,
    hidden_layer: DenseLayer,
    output_layer: DenseLayer,
}

#[near]
impl NeuralNetworkContract {
    #[init]
    pub fn new_xor_demo() -> Self {
        let scale = 1_000;
        Self {
            scale,
            hidden_layer: DenseLayer {
                weights: vec![vec![scale, scale], vec![scale, scale]],
                biases: vec![0, -scale],
            },
            output_layer: DenseLayer {
                weights: vec![vec![scale, -2 * scale]],
                biases: vec![0],
            },
        }
    }

    pub fn model_info(&self) -> ModelInfo {
        ModelInfo {
            input_size: self.input_size(),
            hidden_size: self.hidden_layer.biases.len(),
            output_size: self.output_layer.biases.len(),
            scale: self.scale,
            description: "Two-layer fixed-point MLP compiled to WASM and deployed on NEAR. Inputs are scaled integers where 0 means false and 1000 means true.".to_string(),
        }
    }

    pub fn predict(&self, inputs: Vec<i32>) -> Prediction {
        self.assert_input_shape(&inputs);
        let hidden = self.run_layer(&self.hidden_layer, &inputs, true);
        let output = self.run_layer(&self.output_layer, &hidden, false);
        Prediction {
            predicted_class: output[0] >= self.scale / 2,
            hidden_layer: hidden,
            output_layer: output,
        }
    }

    pub fn xor_truth_table(&self) -> Vec<Prediction> {
        vec![
            self.predict(vec![0, 0]),
            self.predict(vec![self.scale, 0]),
            self.predict(vec![0, self.scale]),
            self.predict(vec![self.scale, self.scale]),
        ]
    }
}

impl NeuralNetworkContract {
    fn input_size(&self) -> usize {
        self.hidden_layer
            .weights
            .first()
            .map(|row| row.len())
            .unwrap_or(0)
    }

    fn assert_input_shape(&self, inputs: &[i32]) {
        assert_eq!(
            inputs.len(),
            self.input_size(),
            "expected {} inputs, got {}",
            self.input_size(),
            inputs.len()
        );
    }

    fn run_layer(&self, layer: &DenseLayer, inputs: &[i32], relu: bool) -> Vec<i32> {
        layer
            .weights
            .iter()
            .zip(&layer.biases)
            .map(|(weights, bias)| {
                let sum =
                    weights
                        .iter()
                        .zip(inputs.iter())
                        .fold(*bias as i64, |acc, (weight, input)| {
                            acc + ((*weight as i64) * (*input as i64) / self.scale as i64)
                        });
                let value = clamp_to_i32(sum);
                if relu {
                    value.max(0)
                } else {
                    value.clamp(0, self.scale)
                }
            })
            .collect()
    }
}

fn clamp_to_i32(value: i64) -> i32 {
    value.clamp(i32::MIN as i64, i32::MAX as i64) as i32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn predicts_xor_truth_table() {
        let contract = NeuralNetworkContract::new_xor_demo();

        let cases = [
            (vec![0, 0], false),
            (vec![1_000, 0], true),
            (vec![0, 1_000], true),
            (vec![1_000, 1_000], false),
        ];

        for (inputs, expected) in cases {
            let prediction = contract.predict(inputs.clone());
            assert_eq!(prediction.predicted_class, expected, "inputs: {inputs:?}");
        }
    }

    #[test]
    fn exposes_model_metadata() {
        let contract = NeuralNetworkContract::new_xor_demo();
        let info = contract.model_info();

        assert_eq!(info.input_size, 2);
        assert_eq!(info.hidden_size, 2);
        assert_eq!(info.output_size, 1);
        assert_eq!(info.scale, 1_000);
    }
}
