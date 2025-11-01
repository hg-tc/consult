import asyncio
from typing import Dict, Any, AsyncIterator
import time


class ProgressBroker:
    def __init__(self):
        self._topic_queues: Dict[str, asyncio.Queue] = {}

    def _key(self, topic: str, workspace_id: str) -> str:
        return f"{topic}:{workspace_id}"

    def _get_queue(self, topic: str, workspace_id: str) -> asyncio.Queue:
        key = self._key(topic, workspace_id)
        if key not in self._topic_queues:
            self._topic_queues[key] = asyncio.Queue(maxsize=100)
        return self._topic_queues[key]

    async def publish(self, topic: str, workspace_id: str, event: Dict[str, Any]):
        q = self._get_queue(topic, workspace_id)
        payload = {
            **event,
            "topic": topic,
            "workspace_id": workspace_id,
            "ts": event.get("ts") or time.time(),
        }
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # 丢弃最旧，保最新
            try:
                _ = q.get_nowait()
            except Exception:
                pass
            q.put_nowait(payload)

    async def stream(self, topic: str, workspace_id: str) -> AsyncIterator[Dict[str, Any]]:
        q = self._get_queue(topic, workspace_id)
        while True:
            data = await q.get()
            yield data


_broker: ProgressBroker | None = None


def get_progress_broker() -> ProgressBroker:
    global _broker
    if _broker is None:
        _broker = ProgressBroker()
    return _broker


