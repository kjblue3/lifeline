
import os
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_PATH = os.path.abspath(r".\models\qwen2.5-3b")

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    local_files_only=True
)

print("Loading Qwen2.5 3B on CPU...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.float32,
    low_cpu_mem_usage=True,
    local_files_only=True
)
model.eval()

messages = [
    {
        "role": "system",
        "content": (
            "You are LifeLine, an offline wilderness safety information assistant. "
            "Do not claim to diagnose injuries. For emergencies, advise users "
            "to seek emergency assistance when possible."
        )
    },
    {
        "role": "user",
        "content": "What are three important things to pack for a day hike?"
    }
]

inputs = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True
)

print("Generating answer...")
start = time.perf_counter()

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=80,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id
    )

elapsed = time.perf_counter() - start

new_tokens = outputs[0][inputs["input_ids"].shape[-1]:]
answer = tokenizer.decode(new_tokens, skip_special_tokens=True)

print("\nLifeLine answer:")
print(answer)
print(f"\nGeneration time: {elapsed:.2f} seconds")
print(f"Generated tokens: {len(new_tokens)}")
