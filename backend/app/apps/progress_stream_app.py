from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator
import json

from app.utils.progress_broker import get_progress_broker


router = APIRouter()


async def sse_event_generator(topic: str, workspace_id: str) -> AsyncIterator[bytes]:
    broker = get_progress_broker()
    async for event in broker.stream(topic, workspace_id):
        data = json.dumps(event, ensure_ascii=False)
        yield f"data: {data}\n\n".encode("utf-8")


@router.get("/api/v1/stream/progress")
async def stream_progress(request: Request, topic: str, workspace_id: str):
    if not topic or not workspace_id:
        raise HTTPException(status_code=400, detail="topic 与 workspace_id 必填")
    generator = sse_event_generator(topic, workspace_id)
    return StreamingResponse(generator, media_type="text/event-stream")


