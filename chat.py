"""LifeLine local-only chat API. No cloud inference or network fallback."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from inference import InferenceError, InferenceProvider, SAFETY_NOTICE
from local_adapter import LocalAIAdapter

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


@router.get('/health')
async def health():
    return {'ok': True, 'data': {'status': 'ok', 'service': 'lifeline'}}


@router.get('/status')
async def status():
    return {'ok': True, 'data': {
        'mode': 'local' if provider.configured and provider.ready else 'unavailable',
        'cloud': {'enabled': False, 'configured': False, 'ready': False},
        'local': {'configured': provider.configured, 'ready': provider.ready,
                  'model': provider.model,
                  'message': 'Local AI ready' if provider.configured and provider.ready
                  else 'Local AI not connected'},
        'references': {'installed': False, 'count': 0},
        'offline_ready': False,
    }}


@router.post('/ask')
async def ask(payload: Question):
    try:
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
