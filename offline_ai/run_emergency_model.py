import json
import re
from pathlib import Path

import torch
from executorch.runtime import Runtime

folder = Path(__file__).resolve().parent
metadata = json.loads(
    (folder / "emergency_classifier_meta.json").read_text(encoding="utf-8")
)

vocab = metadata["vocab"]
labels = metadata["labels"]
lookup = {word: i for i, word in enumerate(vocab)}

runtime = Runtime.get()
program = runtime.load_program(str(folder / "emergency_classifier.pte"))
method = program.load_method("forward")

def classify(text):
    vector = torch.zeros(1, len(vocab))
    for word in set(re.findall(r"[a-z]+", text.lower())):
        if word in lookup:
            vector[0, lookup[word]] = 1.0

    outputs = method.execute([vector])
    predicted = outputs[0].argmax(dim=1).item()
    return labels[predicted]

tests = [
    "My friend is bleeding",
    "We are stranded in the mountains",
    "There is a wildfire nearby",
    "We need drinking water",
]

for question in tests:
    print("INPUT:", question)
    print("EXECUTORCH PREDICTION:", classify(question))
    print("---")

print("SUCCESS: ExecuTorch classifier executed")
