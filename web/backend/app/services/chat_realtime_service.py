import json
from collections import defaultdict

from fastapi import WebSocket


class ConsultationRealtimeHub:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, consultation_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections[consultation_id].add(websocket)

    def disconnect(self, consultation_id: str, websocket: WebSocket):
        connections = self._connections.get(consultation_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(consultation_id, None)

    async def broadcast_message(self, consultation_id: str, message: dict):
        payload = json.dumps({"type": "message", "message": message})
        stale_connections = []
        for websocket in list(self._connections.get(consultation_id, set())):
            try:
                await websocket.send_text(payload)
            except Exception:
                stale_connections.append(websocket)
        for websocket in stale_connections:
            self.disconnect(consultation_id, websocket)


realtime_hub = ConsultationRealtimeHub()
