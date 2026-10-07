from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.ai.llm_provider import LLMProviderError
from app.api.deps import ensure_llm_ready, get_chat_service
from app.core.rate_limit import rate_limit
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(rate_limit("chat", "rate_limit_chat_per_minute"))])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    ensure_llm_ready()
    try:
        return await service.answer(req)
    except LLMProviderError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.post("/stream")
def chat_stream(req: ChatRequest, service: ChatService = Depends(get_chat_service)) -> StreamingResponse:
    ensure_llm_ready()
    return StreamingResponse(
        service.stream_events(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
