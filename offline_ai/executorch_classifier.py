"""Offline ExecuTorch category classifier. Experimental, not medical triage."""

import json
import re
from pathlib import Path
from threading import Lock

import torch
from executorch.runtime import Runtime

FOLDER = Path(__file__).resolve().parent

metadata = json.loads(
    (FOLDER / "emergency_classifier_meta.json").read_text(encoding="utf-8")
)

LABELS = metadata["labels"]
VOCAB = {word: i for i, word in enumerate(metadata["vocab"])}

runtime = Runtime.get()
program = runtime.load_program(str(FOLDER / "emergency_classifier.pte"))
method = program.load_method("forward")
lock = Lock()

def predict_category(text: str):
    vector = torch.zeros(1, len(VOCAB), dtype=torch.float32)
    matched = 0

    for word in set(re.findall(r"[a-z]+", text.lower())):
        if word in VOCAB:
            vector[0, VOCAB[word]] = 1.0
            matched += 1

    if matched == 0:
        return None

    with lock:
        result = method.execute([vector])

    index = int(result[0].argmax(dim=1).item())
    return LABELS[index]
