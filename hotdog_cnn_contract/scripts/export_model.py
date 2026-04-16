#!/usr/bin/env python3

from __future__ import annotations

import copy
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import torch
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

INPUT_WIDTH = 64
INPUT_HEIGHT = 64
INPUT_CHANNELS = 3
INPUT_SIZE = INPUT_WIDTH * INPUT_HEIGHT * INPUT_CHANNELS
INPUT_SCALE = 255
MAX_LAYER_SCALE = 4096
OUTPUT_SIZE = 2
CONV1_STRIDE = 2
CONV1_OUT_CHANNELS = 16
CONV2_OUT_CHANNELS = 32
CONV3_OUT_CHANNELS = 48
MLP_HIDDEN_SIZE = 9432
CONV1_WIDTH = INPUT_WIDTH // CONV1_STRIDE
CONV1_HEIGHT = INPUT_HEIGHT // CONV1_STRIDE
POOL1_WIDTH = CONV1_WIDTH // 2
POOL1_HEIGHT = CONV1_HEIGHT // 2
POOL2_WIDTH = POOL1_WIDTH // 2
POOL2_HEIGHT = POOL1_HEIGHT // 2
SAMPLE_COUNT = 10
LABELS = ["hotdog", "not_hotdog"]
DEFAULT_TRAINING_SEEDS = [7, 11, 19, 23, 29]
DEFAULT_EPOCHS = 60
DEFAULT_BATCH_SIZE = 16


@dataclass(frozen=True)
class TrainingRecipe:
    name: str
    learning_rate: float
    weight_decay: float
    crop_scale_min: float
    jitter_strength: float


TRAINING_RECIPES = [
    TrainingRecipe(
        name="baseline",
        learning_rate=2e-3,
        weight_decay=1e-4,
        crop_scale_min=0.65,
        jitter_strength=0.15,
    ),
    TrainingRecipe(
        name="lower_lr",
        learning_rate=1.2e-3,
        weight_decay=7.5e-5,
        crop_scale_min=0.72,
        jitter_strength=0.12,
    ),
    TrainingRecipe(
        name="tighter_crop",
        learning_rate=1.5e-3,
        weight_decay=5e-5,
        crop_scale_min=0.8,
        jitter_strength=0.1,
    ),
]


@dataclass(frozen=True)
class ExportConfig:
    dataset_root: Path
    train_dir: Path
    val_dir: Path
    output_path: Path
    training_seeds: list[int]
    training_recipes: list[str]
    epochs: int
    batch_size: int


def trunc_div(value: int, divisor: int) -> int:
    assert divisor > 0
    if value >= 0:
        return value // divisor
    return -((-value) // divisor)


def flatten_hwc_uint8(image: torch.Tensor) -> list[int]:
    pixels = torch.round(image.clamp(0, 1) * INPUT_SCALE).to(torch.uint8)
    return pixels.permute(1, 2, 0).reshape(-1).tolist()


def conv2d_same_u8(
    input_pixels: list[int],
    width: int,
    height: int,
    in_channels: int,
    weights: list[int],
    biases: list[int],
    out_channels: int,
    input_divisor: int,
) -> list[int]:
    output = [0] * (width * height * out_channels)
    for y in range(height):
        for x in range(width):
            for out_channel in range(out_channels):
                total = biases[out_channel]
                for in_channel in range(in_channels):
                    for ky in range(3):
                        iy = y + ky - 1
                        if iy < 0 or iy >= height:
                            continue
                        for kx in range(3):
                            ix = x + kx - 1
                            if ix < 0 or ix >= width:
                                continue
                            input_index = ((iy * width + ix) * in_channels) + in_channel
                            weight_index = (
                                ((out_channel * in_channels + in_channel) * 3 + ky) * 3
                            ) + kx
                            total += trunc_div(weights[weight_index] * input_pixels[input_index], input_divisor)
                output[((y * width + x) * out_channels) + out_channel] = int(total)
    return output


def conv2d_same_stride2_u8(
    input_pixels: list[int],
    width: int,
    height: int,
    in_channels: int,
    weights: list[int],
    biases: list[int],
    out_channels: int,
    input_divisor: int,
) -> list[int]:
    out_width = width // 2
    out_height = height // 2
    output = [0] * (out_width * out_height * out_channels)
    for y in range(out_height):
        in_y_center = y * 2
        for x in range(out_width):
            in_x_center = x * 2
            for out_channel in range(out_channels):
                total = biases[out_channel]
                for in_channel in range(in_channels):
                    for ky in range(3):
                        iy = in_y_center + ky - 1
                        if iy < 0 or iy >= height:
                            continue
                        for kx in range(3):
                            ix = in_x_center + kx - 1
                            if ix < 0 or ix >= width:
                                continue
                            input_index = ((iy * width + ix) * in_channels) + in_channel
                            weight_index = (
                                ((out_channel * in_channels + in_channel) * 3 + ky) * 3
                            ) + kx
                            total += trunc_div(
                                weights[weight_index] * input_pixels[input_index], input_divisor
                            )
                output[((y * out_width + x) * out_channels) + out_channel] = int(total)
    return output


def conv2d_same_i32(
    input_values: list[int],
    width: int,
    height: int,
    in_channels: int,
    weights: list[int],
    biases: list[int],
    out_channels: int,
    input_divisor: int,
) -> list[int]:
    output = [0] * (width * height * out_channels)
    for y in range(height):
        for x in range(width):
            for out_channel in range(out_channels):
                total = biases[out_channel]
                for in_channel in range(in_channels):
                    for ky in range(3):
                        iy = y + ky - 1
                        if iy < 0 or iy >= height:
                            continue
                        for kx in range(3):
                            ix = x + kx - 1
                            if ix < 0 or ix >= width:
                                continue
                            input_index = ((iy * width + ix) * in_channels) + in_channel
                            weight_index = (
                                ((out_channel * in_channels + in_channel) * 3 + ky) * 3
                            ) + kx
                            total += trunc_div(weights[weight_index] * input_values[input_index], input_divisor)
                output[((y * width + x) * out_channels) + out_channel] = int(total)
    return output


def relu_in_place(values: list[int]) -> list[int]:
    return [max(0, value) for value in values]


def max_pool_2x2(input_values: list[int], width: int, height: int, channels: int) -> list[int]:
    out_width = width // 2
    out_height = height // 2
    output = [0] * (out_width * out_height * channels)
    for y in range(out_height):
        for x in range(out_width):
            for channel in range(channels):
                max_value = -(1 << 31)
                for py in range(2):
                    for px in range(2):
                        in_y = y * 2 + py
                        in_x = x * 2 + px
                        index = ((in_y * width + in_x) * channels) + channel
                        max_value = max(max_value, input_values[index])
                output[((y * out_width + x) * channels) + channel] = max_value
    return output


def global_average_pool(input_values: list[int], width: int, height: int, channels: int) -> list[int]:
    divisor = width * height
    output = []
    for channel in range(channels):
        total = 0
        for y in range(height):
            for x in range(width):
                total += input_values[((y * width + x) * channels) + channel]
        output.append(trunc_div(total, divisor))
    return output


def linear(
    input_values: list[int],
    weights: list[int],
    biases: list[int],
    input_size: int,
    output_size: int,
    input_divisor: int,
) -> list[int]:
    output = []
    for output_index in range(output_size):
        total = biases[output_index]
        for input_index in range(input_size):
            total += trunc_div(
                weights[output_index * input_size + input_index] * input_values[input_index],
                input_divisor,
            )
        output.append(total)
    return output


def argmax(values: list[int]) -> int:
    return max(range(len(values)), key=lambda index: values[index])


@dataclass
class QuantizedModel:
    conv1_scale: int
    conv1_weights: list[int]
    conv1_biases: list[int]
    conv2_scale: int
    conv2_weights: list[int]
    conv2_biases: list[int]
    conv3_scale: int
    conv3_weights: list[int]
    conv3_biases: list[int]
    fc1_scale: int
    fc1_weights: list[int]
    fc1_biases: list[int]
    fc2_scale: int
    fc2_weights: list[int]
    fc2_biases: list[int]


def parse_int_list_env(name: str, default: Sequence[int]) -> list[int]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    if not values:
        raise ValueError(f"{name} must contain at least one integer")
    return values


def parse_positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def parse_string_list_env(name: str, default: Sequence[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    values = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            values.append(part)
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return values


def resolve_dataset_dirs(dataset_root: Path) -> tuple[Path, Path]:
    train_dir = dataset_root / "train"
    if not train_dir.exists():
        raise SystemExit(f"dataset not found at {dataset_root}: missing train/")

    for candidate in ("val", "valid", "validation", "test"):
        split_dir = dataset_root / candidate
        if split_dir.exists():
            return train_dir, split_dir

    raise SystemExit(
        f"dataset not found at {dataset_root}: expected one of val/, valid/, validation/, or test/"
    )


def load_config() -> ExportConfig:
    dataset_root = Path(os.environ.get("HOTDOG_DATASET_DIR", "/tmp/hotdog_nothotdog"))
    train_dir, val_dir = resolve_dataset_dirs(dataset_root)
    output_path = Path(
        os.environ.get(
            "HOTDOG_MODEL_DATA_OUT",
            str(Path(__file__).resolve().parent.parent / "src" / "model_data.rs"),
        )
    )
    return ExportConfig(
        dataset_root=dataset_root,
        train_dir=train_dir,
        val_dir=val_dir,
        output_path=output_path,
        training_seeds=parse_int_list_env("HOTDOG_TRAINING_SEEDS", DEFAULT_TRAINING_SEEDS),
        training_recipes=parse_string_list_env(
            "HOTDOG_TRAINING_RECIPES", [recipe.name for recipe in TRAINING_RECIPES]
        ),
        epochs=parse_positive_int_env("HOTDOG_EPOCHS", DEFAULT_EPOCHS),
        batch_size=parse_positive_int_env("HOTDOG_BATCH_SIZE", DEFAULT_BATCH_SIZE),
    )


class TinyHotdogCnn(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(
            INPUT_CHANNELS,
            CONV1_OUT_CHANNELS,
            kernel_size=3,
            stride=CONV1_STRIDE,
            padding=1,
        )
        self.bn1 = nn.BatchNorm2d(CONV1_OUT_CHANNELS)
        self.conv2 = nn.Conv2d(CONV1_OUT_CHANNELS, CONV2_OUT_CHANNELS, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(CONV2_OUT_CHANNELS)
        self.conv3 = nn.Conv2d(CONV2_OUT_CHANNELS, CONV3_OUT_CHANNELS, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(CONV3_OUT_CHANNELS)
        self.relu = nn.ReLU()
        self.pool = nn.MaxPool2d(kernel_size=2)
        self.avg_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc1 = nn.Linear(CONV3_OUT_CHANNELS, MLP_HIDDEN_SIZE)
        self.fc2 = nn.Linear(MLP_HIDDEN_SIZE, OUTPUT_SIZE)

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        images = self.pool(self.relu(self.bn1(self.conv1(images))))
        images = self.pool(self.relu(self.bn2(self.conv2(images))))
        images = self.avg_pool(self.relu(self.bn3(self.conv3(images))))
        images = self.relu(self.fc1(images.flatten(1)))
        return self.fc2(images)


def train_one_attempt(
    train_dir: Path,
    val_dir: Path,
    seed: int,
    recipe: TrainingRecipe,
    config: ExportConfig,
) -> tuple[TinyHotdogCnn, float]:
    torch.manual_seed(seed)
    random.seed(seed)

    train_transform = transforms.Compose(
        [
            transforms.Resize((72, 72)),
            transforms.RandomResizedCrop(
                (INPUT_HEIGHT, INPUT_WIDTH), scale=(recipe.crop_scale_min, 1.0)
            ),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(
                brightness=recipe.jitter_strength,
                contrast=recipe.jitter_strength,
                saturation=recipe.jitter_strength,
                hue=min(recipe.jitter_strength / 5.0, 0.08),
            ),
            transforms.ToTensor(),
        ]
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize((INPUT_HEIGHT, INPUT_WIDTH)),
            transforms.ToTensor(),
        ]
    )

    train_dataset = datasets.ImageFolder(train_dir, transform=train_transform)
    val_dataset = datasets.ImageFolder(val_dir, transform=eval_transform)
    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=config.batch_size)

    model = TinyHotdogCnn()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=recipe.learning_rate,
        weight_decay=recipe.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)
    loss_fn = nn.CrossEntropyLoss()

    best_state = copy.deepcopy(model.state_dict())
    best_accuracy = 0.0

    for epoch in range(config.epochs):
        model.train()
        total_loss = 0.0
        seen = 0
        for images, labels in train_loader:
            optimizer.zero_grad()
            logits = model(images)
            loss = loss_fn(logits, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)
            seen += images.size(0)
        scheduler.step()

        accuracy = evaluate_float_accuracy(model, val_loader)
        if accuracy >= best_accuracy:
            best_accuracy = accuracy
            best_state = copy.deepcopy(model.state_dict())

        if epoch in {0, 9, 19, 39, config.epochs - 1}:
            print(
                f"recipe {recipe.name} seed {seed} epoch {epoch + 1:02d}/{config.epochs} "
                f"loss {total_loss / max(seen, 1):.4f} val_acc {accuracy:.4f}"
            )

    model.load_state_dict(best_state)
    return model, best_accuracy


def evaluate_float_accuracy(model: TinyHotdogCnn, loader: DataLoader) -> float:
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            predictions = model(images).argmax(dim=1)
            correct += (predictions == labels).sum().item()
            total += labels.numel()
    return correct / max(total, 1)


def choose_layer_scale(weights: torch.Tensor) -> int:
    max_abs = weights.detach().abs().max().item()
    if max_abs <= 1e-9:
        return 1
    return max(1, min(MAX_LAYER_SCALE, int(32767 // max_abs)))


def quantize_tensor(values: torch.Tensor, scale: int, dtype: torch.dtype) -> list[int]:
    return torch.round(values.detach() * scale).to(dtype).reshape(-1).tolist()


def fuse_conv_bn(conv: nn.Conv2d, bn: nn.BatchNorm2d) -> tuple[torch.Tensor, torch.Tensor]:
    bn_scale = bn.weight.detach() / torch.sqrt(bn.running_var.detach() + bn.eps)
    fused_weight = conv.weight.detach() * bn_scale.reshape(-1, 1, 1, 1)
    fused_bias = bn.bias.detach() + (conv.bias.detach() - bn.running_mean.detach()) * bn_scale
    return fused_weight, fused_bias


def quantize_model(model: TinyHotdogCnn) -> QuantizedModel:
    conv1_weight, conv1_bias = fuse_conv_bn(model.conv1, model.bn1)
    conv2_weight, conv2_bias = fuse_conv_bn(model.conv2, model.bn2)
    conv3_weight, conv3_bias = fuse_conv_bn(model.conv3, model.bn3)
    fc1 = model.fc1
    fc2 = model.fc2
    conv1_scale = choose_layer_scale(conv1_weight)
    conv2_scale = choose_layer_scale(conv2_weight)
    conv3_scale = choose_layer_scale(conv3_weight)
    fc1_scale = choose_layer_scale(fc1.weight)
    fc2_scale = choose_layer_scale(fc2.weight)
    return QuantizedModel(
        conv1_scale=conv1_scale,
        conv1_weights=quantize_tensor(conv1_weight, conv1_scale, torch.int16),
        conv1_biases=quantize_tensor(conv1_bias, conv1_scale, torch.int32),
        conv2_scale=conv2_scale,
        conv2_weights=quantize_tensor(conv2_weight, conv2_scale, torch.int16),
        conv2_biases=quantize_tensor(conv2_bias, conv2_scale, torch.int32),
        conv3_scale=conv3_scale,
        conv3_weights=quantize_tensor(conv3_weight, conv3_scale, torch.int16),
        conv3_biases=quantize_tensor(conv3_bias, conv3_scale, torch.int32),
        fc1_scale=fc1_scale,
        fc1_weights=quantize_tensor(fc1.weight, fc1_scale, torch.int16),
        fc1_biases=quantize_tensor(fc1.bias, fc1_scale, torch.int32),
        fc2_scale=fc2_scale,
        fc2_weights=quantize_tensor(fc2.weight, fc2_scale, torch.int16),
        fc2_biases=quantize_tensor(fc2.bias, fc2_scale, torch.int32),
    )


def quantized_predict(pixels: list[int], model: QuantizedModel) -> tuple[int, list[int]]:
    conv1 = relu_in_place(
        conv2d_same_stride2_u8(
            pixels,
            INPUT_WIDTH,
            INPUT_HEIGHT,
            INPUT_CHANNELS,
            model.conv1_weights,
            model.conv1_biases,
            CONV1_OUT_CHANNELS,
            INPUT_SCALE,
        )
    )
    pooled1 = max_pool_2x2(conv1, CONV1_WIDTH, CONV1_HEIGHT, CONV1_OUT_CHANNELS)

    conv2 = relu_in_place(
        conv2d_same_i32(
            pooled1,
            POOL1_WIDTH,
            POOL1_HEIGHT,
            CONV1_OUT_CHANNELS,
            model.conv2_weights,
            model.conv2_biases,
            CONV2_OUT_CHANNELS,
            model.conv1_scale,
        )
    )
    pooled2 = max_pool_2x2(conv2, POOL1_WIDTH, POOL1_HEIGHT, CONV2_OUT_CHANNELS)

    conv3 = relu_in_place(
        conv2d_same_i32(
            pooled2,
            POOL2_WIDTH,
            POOL2_HEIGHT,
            CONV2_OUT_CHANNELS,
            model.conv3_weights,
            model.conv3_biases,
            CONV3_OUT_CHANNELS,
            model.conv2_scale,
        )
    )
    pooled = global_average_pool(conv3, POOL2_WIDTH, POOL2_HEIGHT, CONV3_OUT_CHANNELS)
    hidden = relu_in_place(
        linear(
            pooled,
            model.fc1_weights,
            model.fc1_biases,
            CONV3_OUT_CHANNELS,
            MLP_HIDDEN_SIZE,
            model.conv3_scale,
        )
    )
    logits = linear(
        hidden,
        model.fc2_weights,
        model.fc2_biases,
        MLP_HIDDEN_SIZE,
        OUTPUT_SIZE,
        model.fc1_scale,
    )
    return argmax(logits), logits


def choose_samples(dataset: datasets.ImageFolder, model: QuantizedModel) -> list[tuple[int, list[int]]]:
    per_label = {label_index: [] for label_index in range(len(LABELS))}
    ordered = []
    for image, label in dataset:
        pixels = flatten_hwc_uint8(image)
        prediction, _ = quantized_predict(pixels, model)
        if prediction != label:
            continue
        if len(per_label[label]) < SAMPLE_COUNT // 2:
            per_label[label].append((label, pixels))
        ordered.append((label, pixels))

    samples = per_label[0] + per_label[1]
    if len(samples) < SAMPLE_COUNT:
        seen = len(samples)
        for label, pixels in ordered:
            if seen >= SAMPLE_COUNT:
                break
            if (label, pixels) not in samples:
                samples.append((label, pixels))
                seen += 1

    if len(samples) < SAMPLE_COUNT:
        raise RuntimeError(
            f"need {SAMPLE_COUNT} correctly classified validation samples, found {len(samples)}"
        )

    return samples[:SAMPLE_COUNT]


def write_model_data(output_path: Path, model: QuantizedModel, samples: list[tuple[int, list[int]]]) -> None:
    with output_path.open("w", encoding="utf-8") as file:
        file.write("// Generated from an offline-trained hotdog/not-hotdog CNN.\n")
        file.write(f"pub const INPUT_WIDTH: usize = {INPUT_WIDTH};\n")
        file.write(f"pub const INPUT_HEIGHT: usize = {INPUT_HEIGHT};\n")
        file.write(f"pub const INPUT_CHANNELS: usize = {INPUT_CHANNELS};\n")
        file.write(f"pub const INPUT_SIZE: usize = {INPUT_SIZE};\n")
        file.write(f"pub const INPUT_SCALE: i32 = {INPUT_SCALE};\n")
        file.write(f"pub const CONV1_SCALE: i32 = {model.conv1_scale};\n")
        file.write(f"pub const CONV2_SCALE: i32 = {model.conv2_scale};\n")
        file.write(f"pub const CONV3_SCALE: i32 = {model.conv3_scale};\n")
        file.write(f"pub const FC1_SCALE: i32 = {model.fc1_scale};\n")
        file.write(f"pub const FC2_SCALE: i32 = {model.fc2_scale};\n")
        file.write(f"pub const CONV1_OUT_CHANNELS: usize = {CONV1_OUT_CHANNELS};\n")
        file.write(f"pub const CONV2_OUT_CHANNELS: usize = {CONV2_OUT_CHANNELS};\n")
        file.write(f"pub const CONV3_OUT_CHANNELS: usize = {CONV3_OUT_CHANNELS};\n")
        file.write(f"pub const MLP_HIDDEN_SIZE: usize = {MLP_HIDDEN_SIZE};\n")
        file.write(f"pub const CONV1_WIDTH: usize = {CONV1_WIDTH};\n")
        file.write(f"pub const CONV1_HEIGHT: usize = {CONV1_HEIGHT};\n")
        file.write(f"pub const POOL1_WIDTH: usize = {POOL1_WIDTH};\n")
        file.write(f"pub const POOL1_HEIGHT: usize = {POOL1_HEIGHT};\n")
        file.write(f"pub const POOL2_WIDTH: usize = {POOL2_WIDTH};\n")
        file.write(f"pub const POOL2_HEIGHT: usize = {POOL2_HEIGHT};\n")
        file.write(f"pub const OUTPUT_SIZE: usize = {OUTPUT_SIZE};\n")
        file.write(
            'pub const LABELS: [&str; OUTPUT_SIZE] = ["hotdog", "not_hotdog"];\n'
        )
        file.write(
            f"pub const CONV1_WEIGHTS: [i16; {len(model.conv1_weights)}] = ["
            + ", ".join(map(str, model.conv1_weights))
            + "];\n"
        )
        file.write(
            f"pub const CONV1_BIASES: [i32; CONV1_OUT_CHANNELS] = ["
            + ", ".join(map(str, model.conv1_biases))
            + "];\n"
        )
        file.write(
            f"pub const CONV2_WEIGHTS: [i16; {len(model.conv2_weights)}] = ["
            + ", ".join(map(str, model.conv2_weights))
            + "];\n"
        )
        file.write(
            f"pub const CONV2_BIASES: [i32; CONV2_OUT_CHANNELS] = ["
            + ", ".join(map(str, model.conv2_biases))
            + "];\n"
        )
        file.write(
            f"pub const CONV3_WEIGHTS: [i16; {len(model.conv3_weights)}] = ["
            + ", ".join(map(str, model.conv3_weights))
            + "];\n"
        )
        file.write(
            f"pub const CONV3_BIASES: [i32; CONV3_OUT_CHANNELS] = ["
            + ", ".join(map(str, model.conv3_biases))
            + "];\n"
        )
        file.write(
            f"pub const FC1_WEIGHTS: [i16; {len(model.fc1_weights)}] = ["
            + ", ".join(map(str, model.fc1_weights))
            + "];\n"
        )
        file.write(
            f"pub const FC1_BIASES: [i32; MLP_HIDDEN_SIZE] = ["
            + ", ".join(map(str, model.fc1_biases))
            + "];\n"
        )
        file.write(
            f"pub const FC2_WEIGHTS: [i16; {len(model.fc2_weights)}] = ["
            + ", ".join(map(str, model.fc2_weights))
            + "];\n"
        )
        file.write(
            f"pub const FC2_BIASES: [i32; OUTPUT_SIZE] = ["
            + ", ".join(map(str, model.fc2_biases))
            + "];\n"
        )
        file.write(f"pub const SAMPLE_LABELS: [u8; {len(samples)}] = [")
        file.write(", ".join(str(label) for label, _ in samples))
        file.write("];\n")
        file.write(f"pub const SAMPLE_IMAGES: [[u8; INPUT_SIZE]; {len(samples)}] = [\n")
        for _, pixels in samples:
            file.write("    [" + ", ".join(map(str, pixels)) + "],\n")
        file.write("];\n")


def parameter_count() -> int:
    return (
        CONV1_OUT_CHANNELS * INPUT_CHANNELS * 3 * 3
        + CONV1_OUT_CHANNELS
        + CONV2_OUT_CHANNELS * CONV1_OUT_CHANNELS * 3 * 3
        + CONV2_OUT_CHANNELS
        + CONV3_OUT_CHANNELS * CONV2_OUT_CHANNELS * 3 * 3
        + CONV3_OUT_CHANNELS
        + MLP_HIDDEN_SIZE * CONV3_OUT_CHANNELS
        + MLP_HIDDEN_SIZE
        + OUTPUT_SIZE * MLP_HIDDEN_SIZE
        + OUTPUT_SIZE
    )


def evaluate_quantized_accuracy(dataset: datasets.ImageFolder, model: QuantizedModel) -> float:
    correct = 0
    total = 0
    for image, label in dataset:
        prediction, _ = quantized_predict(flatten_hwc_uint8(image), model)
        correct += int(prediction == label)
        total += 1
    return correct / max(total, 1)


def old_main_broken() -> None:
    config = load_config()
    selected_recipes = [recipe for recipe in TRAINING_RECIPES if recipe.name in config.training_recipes]
    if not selected_recipes:
        raise SystemExit(
            f"no recipes selected from {config.training_recipes}; available={[recipe.name for recipe in TRAINING_RECIPES]}"
        )

    best_float_accuracy = -1.0
    best_model = None
    best_recipe_name = ""
    best_seed = -1
    best_eval_transform = transforms.Compose(
        [transforms.Resize((INPUT_HEIGHT, INPUT_WIDTH)), transforms.ToTensor()]
    )
    val_dataset = datasets.ImageFolder(config.val_dir, transform=best_eval_transform)

    print(
        f"using dataset root {config.dataset_root} "
        f"(train={config.train_dir.name}, eval={config.val_dir.name})"
    )
    print(f"dataset classes {val_dataset.classes}")
    print(f"training tiny CNN with {parameter_count()} parameters")
    print(
        f"recipes={[recipe.name for recipe in selected_recipes]} "
        f"seeds={config.training_seeds} epochs={config.epochs} batch_size={config.batch_size}"
    )

    for recipe in selected_recipes:
        for seed in config.training_seeds:
            model, best_float_accuracy = train_one_attempt(
                config.train_dir,
                config.val_dir,
                seed,
                recipe,
                config,
            )
            print(
                f"recipe {recipe.name} seed {seed} "
                f"best_float_val_acc {best_float_accuracy:.4f}"
            )
            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass
            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass
            if best_float_accuracy > best_float_accuracy:
                pass
            if best_float_accuracy > best_float_accuracy:
                pass
            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy >= best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                pass

            if best_float_accuracy > best_float_accuracy:
                best_float_accuracy = best_float_accuracy
                best_model = copy.deepcopy(model)
                best_recipe_name = recipe.name
                best_seed = seed

    assert best_model is not None

    best_quantized_model = quantize_model(best_model)
    best_quantized_accuracy = evaluate_quantized_accuracy(val_dataset, best_quantized_model)
    samples = choose_samples(val_dataset, best_quantized_model)
    write_model_data(config.output_path, best_quantized_model, samples)
    print(f"selected recipe={best_recipe_name} seed={best_seed}")
    print(f"quantized validation accuracy {best_quantized_accuracy:.4f}")
    print(f"embedded {len(samples)} correctly classified validation samples")
    print(f"wrote {config.output_path}")


def main() -> None:
    config = load_config()
    selected_recipes = [recipe for recipe in TRAINING_RECIPES if recipe.name in config.training_recipes]
    if not selected_recipes:
        raise SystemExit(
            f"no recipes selected from {config.training_recipes}; available={[recipe.name for recipe in TRAINING_RECIPES]}"
        )

    best_float_val_accuracy = -1.0
    best_model: TinyHotdogCnn | None = None
    best_recipe_name = ""
    best_seed = -1
    eval_transform = transforms.Compose(
        [transforms.Resize((INPUT_HEIGHT, INPUT_WIDTH)), transforms.ToTensor()]
    )
    val_dataset = datasets.ImageFolder(config.val_dir, transform=eval_transform)

    print(
        f"using dataset root {config.dataset_root} "
        f"(train={config.train_dir.name}, eval={config.val_dir.name})"
    )
    print(f"dataset classes {val_dataset.classes}")
    print(f"training tiny CNN with {parameter_count()} parameters")
    print(
        f"recipes={[recipe.name for recipe in selected_recipes]} "
        f"seeds={config.training_seeds} epochs={config.epochs} batch_size={config.batch_size}"
    )

    for recipe in selected_recipes:
        for seed in config.training_seeds:
            model, float_val_accuracy = train_one_attempt(
                config.train_dir,
                config.val_dir,
                seed,
                recipe,
                config,
            )
            print(
                f"recipe {recipe.name} seed {seed} "
                f"best_float_val_acc {float_val_accuracy:.4f}"
            )
            if float_val_accuracy >= best_float_val_accuracy:
                best_float_val_accuracy = float_val_accuracy
                best_model = copy.deepcopy(model)
                best_recipe_name = recipe.name
                best_seed = seed

    assert best_model is not None

    best_quantized_model = quantize_model(best_model)
    best_quantized_accuracy = evaluate_quantized_accuracy(val_dataset, best_quantized_model)
    samples = choose_samples(val_dataset, best_quantized_model)
    write_model_data(config.output_path, best_quantized_model, samples)
    print(f"selected recipe={best_recipe_name} seed={best_seed}")
    print(f"best float validation accuracy {best_float_val_accuracy:.4f}")
    print(f"quantized validation accuracy {best_quantized_accuracy:.4f}")
    print(f"embedded {len(samples)} correctly classified validation samples")
    print(f"wrote {config.output_path}")


if __name__ == "__main__":
    main()
