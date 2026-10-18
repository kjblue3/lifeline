"""LifeLine local-only chat API. No cloud inference or network fallback."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from inference import InferenceError, InferenceProvider, SAFETY_NOTICE
from local_adapter import LocalAIAdapter
from medical_rag import MedicalLibrary, enabled as rag_enabled, grounded_answer

router = APIRouter(prefix='/api')


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator('question')
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Enter a question before sending.')
        return value


provider: InferenceProvider = LocalAIAdapter()
library = None  # Load reference content only when explicitly enabled.


@router.get('/health')
async def health():
    return {'ok': True, 'data': {'status': 'ok', 'service': 'lifeline'}}


@router.get('/status')
async def status():
    reference_count = (library or MedicalLibrary()).count() if rag_enabled() else 0
    return {'ok': True, 'data': {
        'mode': 'local' if provider.configured and provider.ready else 'unavailable',
        'cloud': {'enabled': False, 'configured': False, 'ready': False},
        'local': {'configured': provider.configured, 'ready': provider.ready,
                  'model': provider.model,
                  'message': 'Local AI ready' if provider.configured and provider.ready
                  else 'Local AI not connected'},
        'references': {'installed': reference_count > 0, 'count': reference_count},
        # Ten topic summaries are not a complete emergency guidance system.
        'offline_ready': False,
    }}


@router.post('/ask')
async def ask(payload: Question):
    try:
        if rag_enabled():
            answer = await grounded_answer(provider, library or MedicalLibrary(), payload.question)
        else:
            answer = await provider.answer(payload.question)
    except InferenceError as exc:
        return JSONResponse(status_code=exc.status_code, content={
            'ok': False, 'error': {'code': exc.code, 'message': str(exc)},
        })
    except Exception:
        return JSONResponse(status_code=500, content={
            'ok': False, 'error': {'code': 'local_inference_failed',
                                 'message': 'Local AI could not complete this request. ' + SAFETY_NOTICE},
        })
    return {'ok': True, 'data': answer.model_dump()}
