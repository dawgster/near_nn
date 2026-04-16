#!/usr/bin/env python3

from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

INPUT_SCALE = 255
WEIGHT_SCALE = 256
INPUT_SIZE = 28 * 28
HIDDEN_SIZE = 24
OUTPUT_SIZE = 10
SEED = 7


def quantized_predict(image, hidden_weights, hidden_biases, output_weights, output_biases):
    pixels = torch.round(image.view(-1) * INPUT_SCALE).to(torch.int32)

    hidden = []
    for neuron_idx in range(hidden_weights.shape[0]):
        total = int(hidden_biases[neuron_idx].item())
        row = hidden_weights[neuron_idx].to(torch.int32)
        total += int(torch.sum((row * pixels) // INPUT_SCALE).item())
        hidden.append(max(0, total))

    hidden = torch.tensor(hidden, dtype=torch.int32)
    logits = []
    for class_idx in range(output_weights.shape[0]):
        total = int(output_biases[class_idx].item())
        row = output_weights[class_idx].to(torch.int32)
        total += int(torch.sum((row * hidden) // WEIGHT_SCALE).item())
        logits.append(total)

    return int(torch.tensor(logits).argmax().item())


def main():
    torch.manual_seed(SEED)

    transform = transforms.ToTensor()
    train = datasets.MNIST("/tmp/mnist-data", train=True, download=True, transform=transform)
    test = datasets.MNIST("/tmp/mnist-data", train=False, download=True, transform=transform)

    train_loader = DataLoader(Subset(train, list(range(30000))), batch_size=256, shuffle=True)
    test_subset = Subset(test, list(range(5000)))
    test_loader = DataLoader(test_subset, batch_size=512)

    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(INPUT_SIZE, HIDDEN_SIZE),
        nn.ReLU(),
        nn.Linear(HIDDEN_SIZE, OUTPUT_SIZE),
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(5):
        model.train()
        total_loss = 0.0
        for images, labels in train_loader:
            optimizer.zero_grad()
            logits = model(images)
            loss = loss_fn(logits, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)
        print(f"epoch {epoch} loss {total_loss / 30000:.4f}")

    model.eval()
    float_correct = 0
    float_total = 0
    with torch.no_grad():
        for images, labels in test_loader:
            predictions = model(images).argmax(dim=1)
            float_correct += (predictions == labels).sum().item()
            float_total += labels.numel()
    print(f"float accuracy {float_correct / float_total:.4f}")

    hidden_layer = model[1]
    output_layer = model[3]
    hidden_weights = torch.round(hidden_layer.weight.detach() * WEIGHT_SCALE).to(torch.int16)
    hidden_biases = torch.round(hidden_layer.bias.detach() * WEIGHT_SCALE).to(torch.int32)
    output_weights = torch.round(output_layer.weight.detach() * WEIGHT_SCALE).to(torch.int16)
    output_biases = torch.round(output_layer.bias.detach() * WEIGHT_SCALE).to(torch.int32)

    quantized_correct = 0
    digit_samples = {}
    for idx in range(len(test)):
        image, label = test[idx]
        label = int(label)
        predicted = quantized_predict(
            image, hidden_weights, hidden_biases, output_weights, output_biases
        )
        if idx < 5000:
            quantized_correct += int(predicted == label)
        if predicted == label and label not in digit_samples:
            digit_samples[label] = torch.round(image.view(-1) * 255).to(torch.uint8).tolist()
        if len(digit_samples) == 10 and idx >= 5000:
            break
    print(f"quantized accuracy {quantized_correct / 5000:.4f}")

    output_path = Path(__file__).resolve().parent.parent / "src" / "model_data.rs"
    with output_path.open("w", encoding="utf-8") as file:
        file.write("// Generated from a tiny offline-trained MNIST MLP.\n")
        file.write(f"pub const INPUT_SCALE: i32 = {INPUT_SCALE};\n")
        file.write(f"pub const WEIGHT_SCALE: i32 = {WEIGHT_SCALE};\n")
        file.write(f"pub const INPUT_SIZE: usize = {INPUT_SIZE};\n")
        file.write(f"pub const HIDDEN_SIZE: usize = {HIDDEN_SIZE};\n")
        file.write(f"pub const OUTPUT_SIZE: usize = {OUTPUT_SIZE};\n")
        file.write("pub const HIDDEN_WEIGHTS: [[i16; INPUT_SIZE]; HIDDEN_SIZE] = [\n")
        for row in hidden_weights.tolist():
            file.write("    [" + ", ".join(map(str, row)) + "],\n")
        file.write("];\n")
        file.write(
            "pub const HIDDEN_BIASES: [i32; HIDDEN_SIZE] = ["
            + ", ".join(map(str, hidden_biases.tolist()))
            + "];\n"
        )
        file.write("pub const OUTPUT_WEIGHTS: [[i16; HIDDEN_SIZE]; OUTPUT_SIZE] = [\n")
        for row in output_weights.tolist():
            file.write("    [" + ", ".join(map(str, row)) + "],\n")
        file.write("];\n")
        file.write(
            "pub const OUTPUT_BIASES: [i32; OUTPUT_SIZE] = ["
            + ", ".join(map(str, output_biases.tolist()))
            + "];\n"
        )
        file.write(
            "pub const SAMPLE_LABELS: [u8; 10] = ["
            + ", ".join(str(i) for i in range(10))
            + "];\n"
        )
        file.write("pub const SAMPLE_IMAGES: [[u8; INPUT_SIZE]; 10] = [\n")
        for digit in range(10):
            file.write("    [" + ", ".join(map(str, digit_samples[digit])) + "],\n")
        file.write("];\n")

    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
