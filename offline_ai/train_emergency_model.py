import json
import re
from pathlib import Path

import torch
from torch import nn
from executorch.exir import to_edge

torch.manual_seed(42)
torch.set_num_threads(2)

examples = {
    "medical": [
        "My friend is bleeding",
        "Someone injured their ankle",
        "A person is unconscious",
        "I have a broken arm",
        "My friend is having chest pain",
        "Someone needs medical help",
        "I have a severe wound",
    ],
    "rescue": [
        "We are stranded in the mountains",
        "Someone is trapped under rocks",
        "We are lost in the forest",
        "Please send a rescue team",
        "Our hiking group cannot get home",
        "We are stuck on a cliff",
        "We need emergency evacuation",
    ],
    "fire": [
        "There is a wildfire nearby",
        "I see smoke in the forest",
        "The campsite is burning",
        "A fire is spreading quickly",
        "Our tent caught fire",
        "Flames are approaching us",
        "There is a forest fire",
    ],
    "supplies": [
        "We need drinking water",
        "Our food supplies are gone",
        "Please bring extra blankets",
        "We need a shelter",
        "Can someone deliver medicine",
        "We ran out of clean water",
        "We need food and warm clothing",
    ],
    "other": [
        "What time is sunset",
        "The scenery is beautiful",
        "I want to plan a hike",
        "Tell me about this mountain",
        "What plants grow here",
        "The trail looks interesting",
        "We are taking photographs",
    ],
}

def tokenize(text):
    return re.findall(r"[a-z]+", text.lower())

labels = list(examples)
samples = [(text, i) for i, label in enumerate(labels)
           for text in examples[label]]
vocab = sorted(set(word for text, _ in samples for word in tokenize(text)))
lookup = {word: i for i, word in enumerate(vocab)}

def encode(text):
    vector = torch.zeros(len(vocab))
    for word in set(tokenize(text)):
        if word in lookup:
            vector[lookup[word]] = 1.0
    return vector

x = torch.stack([encode(text) for text, _ in samples])
y = torch.tensor([label for _, label in samples], dtype=torch.long)

class EmergencyClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(len(vocab), 32),
            nn.ReLU(),
            nn.Linear(32, len(labels)),
        )

    def forward(self, x):
        return self.network(x)

model = EmergencyClassifier()
optimizer = torch.optim.Adam(model.parameters(), lr=0.03)

model.train()
for _ in range(300):
    optimizer.zero_grad()
    loss = nn.functional.cross_entropy(model(x), y)
    loss.backward()
    optimizer.step()

model.eval()
with torch.no_grad():
    accuracy = (model(x).argmax(dim=1) == y).float().mean().item()

print(f"Training accuracy: {accuracy:.1%}")
print(f"Categories: {labels}")
print(f"Vocabulary size: {len(vocab)}")

exported = torch.export.export(model, (torch.zeros(1, len(vocab)),))
program = to_edge(exported).to_executorch()

Path("emergency_classifier.pte").write_bytes(program.buffer)
Path("emergency_classifier_meta.json").write_text(
    json.dumps({"labels": labels, "vocab": vocab}, indent=2),
    encoding="utf-8",
)

print("SUCCESS: emergency_classifier.pte exported")
print("SUCCESS: emergency_classifier_meta.json saved")
