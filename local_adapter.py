"""Integration placeholder, not an AI model or simulated inference.

To connect ExecuTorch, implement inference.InferenceProvider in Kiran's own
adapter and select that instance as chat.provider. No model files are imported,
downloaded, or modified here, and no cloud provider is available as a fallback.
"""
from inference import Answer, InferenceError, SAFETY_NOTICE


class LocalAIAdapter:
    configured = False
    ready = False
    model = None

    async def answer(self, question: str) -> Answer:
        raise InferenceError(
            'local_not_connected',
            'Local AI not connected. The ExecuTorch model has not been integrated. '
            + SAFETY_NOTICE,
        )
