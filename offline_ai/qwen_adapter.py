"""Temporary PyTorch CPU integration; no ExecuTorch or NPU acceleration.

Run from the repository root with:
    python -m uvicorn offline_ai.qwen_adapter:app --host 127.0.0.1 --port 8000
"""

import asyncio
import os
from pathlib import Path
from threading import Lock

from inference import Answer, InferenceError, SAFETY_NOTICE, SYSTEM_INSTRUCTION


class QwenCPUProvider:
    def __init__(self):
        self._model_path = Path(__file__).resolve().parent / 'models' / 'qwen2.5-3b'
        self._tokenizer = None
        self._model = None
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        return (
            (self._model_path / 'config.json').is_file()
            and (self._model_path / 'tokenizer_config.json').is_file()
            and (
                any(self._model_path.glob('model*.safetensors'))
                or any(self._model_path.glob('pytorch_model*.bin'))
            )
        )

    @property
    def ready(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    @property
    def model(self) -> str | None:
        return 'Qwen2.5-3B-Instruct (PyTorch CPU)' if self.configured else None

    async def answer(self, question: str) -> Answer:
        return await asyncio.to_thread(self._answer, question)

    def _answer(self, question: str) -> Answer:
        # Keep ownership in the worker: cancelling an HTTP request cannot unlock
        # a generation that is still running in its background thread.
        if not self._lock.acquire(blocking=False):
            raise InferenceError(
                'local_model_busy', 'Local model is busy. Try again shortly. ' + SAFETY_NOTICE)
        try:
            if not self.ready:
                if not self.configured:
                    raise InferenceError(
                        'local_model_missing',
                        'Install the local Qwen model in offline_ai/models/qwen2.5-3b. '
                        + SAFETY_NOTICE,
                    )
                try:
                    # Set these before lazy imports; local_files_only also
                    # enforces offline loading if HF was imported elsewhere.
                    os.environ['HF_HUB_OFFLINE'] = '1'
                    os.environ['TRANSFORMERS_OFFLINE'] = '1'
                    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
                    import torch
                    from transformers import AutoModelForCausalLM, AutoTokenizer

                    tokenizer = AutoTokenizer.from_pretrained(
                        str(self._model_path), local_files_only=True, trust_remote_code=False)
                    model = AutoModelForCausalLM.from_pretrained(
                        str(self._model_path),
                        torch_dtype=torch.float32,
                        low_cpu_mem_usage=True,
                        local_files_only=True,
                        trust_remote_code=False,
                        device_map=None,
                    )
                    model.to('cpu')
                    model.eval()
                    self._tokenizer = tokenizer
                    self._model = model
                except Exception as exc:
                    raise InferenceError(
                        'local_model_load_failed',
                        'Local Qwen CPU model could not be loaded. ' + SAFETY_NOTICE,
                    ) from exc

            import torch

            inputs = self._tokenizer.apply_chat_template(
                [
                    {'role': 'system', 'content': SYSTEM_INSTRUCTION},
                    {'role': 'user', 'content': question},
                ],
                add_generation_prompt=True,
                return_tensors='pt',
                return_dict=True,
            )
            with torch.inference_mode():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=80,
                    do_sample=False,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            new_tokens = outputs[0][inputs['input_ids'].shape[-1]:]
            text = self._tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            if not text:
                raise InferenceError(
                    'local_empty_answer', 'Local model returned no text. ' + SAFETY_NOTICE)
            return Answer(
                answer=text, mode='local', simulated=False, sources=[], notice=SAFETY_NOTICE)
        except InferenceError:
            raise
        except Exception as exc:
            raise InferenceError(
                'local_inference_failed', 'Local Qwen CPU inference failed. ' + SAFETY_NOTICE,
            ) from exc
        finally:
            self._lock.release()


import chat
from app import app

chat.provider = QwenCPUProvider()
