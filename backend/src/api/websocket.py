"""
WebSocket handler for the Overture system.

Provides real-time bidirectional communication for live updates on ideas,
trades, portfolio changes, agent activity, alerts, and knowledge events.

Channels:
    - ideas: new ideas generated, validation results
    - trades: trade status changes, price updates
    - portfolio: portfolio value changes, risk alerts
    - agents: agent activity, status changes
    - alerts: critical alerts needing attention
    - knowledge: new knowledge entries, outlook updates
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Any
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_CHANNELS = {"ideas", "trades", "portfolio", "agents", "alerts", "knowledge"}


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.subscriptions: dict[str, list[WebSocket]] = {}  # channel -> connections

    async def connect(self, websocket: WebSocket, channels: list[str] | None = None) -> None:
        """Accept a WebSocket connection and subscribe to channels."""
        await websocket.accept()
        self.active_connections.append(websocket)
        if channels:
            for ch in channels:
                if ch in VALID_CHANNELS:
                    self.subscriptions.setdefault(ch, []).append(websocket)
        logger.info(
            "WebSocket connected. Total: %d, Channels: %s",
            len(self.active_connections),
            channels or "none",
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection and clean up subscriptions."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for ch_conns in self.subscriptions.values():
            if websocket in ch_conns:
                ch_conns.remove(websocket)
        logger.info(
            "WebSocket disconnected. Remaining: %d", len(self.active_connections)
        )

    def subscribe(self, websocket: WebSocket, channel: str) -> bool:
        """Subscribe a connection to a channel. Returns True if newly subscribed."""
        if channel not in VALID_CHANNELS:
            return False
        conns = self.subscriptions.setdefault(channel, [])
        if websocket not in conns:
            conns.append(websocket)
            return True
        return False

    def unsubscribe(self, websocket: WebSocket, channel: str) -> bool:
        """Unsubscribe a connection from a channel. Returns True if was subscribed."""
        conns = self.subscriptions.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
            return True
        return False

    def get_subscriptions(self, websocket: WebSocket) -> list[str]:
        """Get all channels a connection is subscribed to."""
        return [ch for ch, conns in self.subscriptions.items() if websocket in conns]

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all subscribers of a channel."""
        payload = {"channel": channel, "data": message}
        disconnected: list[WebSocket] = []
        for conn in self.subscriptions.get(channel, []):
            try:
                await conn.send_json(payload)
            except Exception:
                disconnected.append(conn)
        # Clean up dead connections
        for conn in disconnected:
            await self.disconnect(conn)

    async def broadcast_all(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients regardless of subscriptions."""
        disconnected: list[WebSocket] = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            await self.disconnect(conn)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    @property
    def channel_stats(self) -> dict[str, int]:
        return {ch: len(conns) for ch, conns in self.subscriptions.items() if conns}


# Singleton manager instance used across the application
manager = ConnectionManager()


async def _handle_client_message(websocket: WebSocket, raw: str) -> None:
    """Process an incoming message from a WebSocket client.

    Supported message types:
        subscribe   - {"type": "subscribe", "channels": ["ideas", "trades"]}
        unsubscribe - {"type": "unsubscribe", "channels": ["ideas"]}
        ping        - {"type": "ping"}
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "message": "Invalid JSON"})
        return

    msg_type = msg.get("type")

    if msg_type == "subscribe":
        channels = msg.get("channels", [])
        subscribed: list[str] = []
        invalid: list[str] = []
        for ch in channels:
            if manager.subscribe(websocket, ch):
                subscribed.append(ch)
            elif ch not in VALID_CHANNELS:
                invalid.append(ch)
        response: dict[str, Any] = {
            "type": "subscribed",
            "channels": manager.get_subscriptions(websocket),
        }
        if subscribed:
            response["newly_subscribed"] = subscribed
        if invalid:
            response["invalid_channels"] = invalid
            response["valid_channels"] = sorted(VALID_CHANNELS)
        await websocket.send_json(response)

    elif msg_type == "unsubscribe":
        channels = msg.get("channels", [])
        removed: list[str] = []
        for ch in channels:
            if manager.unsubscribe(websocket, ch):
                removed.append(ch)
        await websocket.send_json({
            "type": "unsubscribed",
            "removed": removed,
            "channels": manager.get_subscriptions(websocket),
        })

    elif msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {msg_type}",
            "supported_types": ["subscribe", "unsubscribe", "ping"],
        })


@router.websocket("/live")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: str | None = Query(None, description="Comma-separated channel names to subscribe to"),
):
    """Main WebSocket endpoint for real-time updates.

    Connect with optional channel subscriptions via query parameter:
        ws://host/ws/live?channels=ideas,trades,portfolio

    Once connected, send JSON messages to subscribe/unsubscribe:
        {"type": "subscribe", "channels": ["agents", "alerts"]}
        {"type": "unsubscribe", "channels": ["ideas"]}
        {"type": "ping"}
    """
    # Parse initial channel subscriptions from query parameter
    initial_channels: list[str] | None = None
    if channels:
        initial_channels = [ch.strip() for ch in channels.split(",") if ch.strip()]

    await manager.connect(websocket, initial_channels)

    # Send welcome message with connection info
    await websocket.send_json({
        "type": "connected",
        "message": "Connected to Overture real-time feed",
        "subscriptions": manager.get_subscriptions(websocket),
        "available_channels": sorted(VALID_CHANNELS),
    })

    try:
        while True:
            # Wait for incoming messages with a timeout for keep-alive
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                await _handle_client_message(websocket, raw)
            except asyncio.TimeoutError:
                # Send keep-alive ping
                try:
                    await websocket.send_json({"type": "keep_alive"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
    finally:
        await manager.disconnect(websocket)
