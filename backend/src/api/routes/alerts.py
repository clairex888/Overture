"""
Alerts API routes.

Provides system alerts for trade approvals, risk warnings, idea updates,
and system notifications.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timedelta
from uuid import uuid4

router = APIRouter()


class AlertResponse(BaseModel):
    id: str
    type: str = Field(..., description="trade, risk, idea, system")
    level: str = Field(..., description="info, warning, critical")
    title: str
    message: str
    action_required: bool
    action_url: str | None = None
    dismissed: bool = False
    created_at: str


class DismissResponse(BaseModel):
    id: str
    dismissed: bool
    message: str


_alerts_store: dict[str, dict[str, Any]] = {}

# Seed alerts
_now = datetime.utcnow()
_seed_alerts = [
    {
        "id": str(uuid4()),
        "type": "trade",
        "level": "critical",
        "title": "Trade Pending Approval",
        "message": "Long NVDA 50 shares @ $890.00 requires manual approval before execution.",
        "action_required": True,
        "action_url": "/trades",
        "dismissed": False,
        "created_at": (_now - timedelta(minutes=5)).isoformat() + "Z",
    },
    {
        "id": str(uuid4()),
        "type": "risk",
        "level": "warning",
        "title": "Concentration Risk",
        "message": "Technology sector exposure at 35%, approaching 40% threshold.",
        "action_required": True,
        "action_url": "/portfolio",
        "dismissed": False,
        "created_at": (_now - timedelta(minutes=32)).isoformat() + "Z",
    },
    {
        "id": str(uuid4()),
        "type": "idea",
        "level": "info",
        "title": "New Idea Validated",
        "message": "Bitcoin ETF inflow thesis validated with 0.88 confidence score.",
        "action_required": False,
        "action_url": "/ideas",
        "dismissed": False,
        "created_at": (_now - timedelta(hours=2)).isoformat() + "Z",
    },
    {
        "id": str(uuid4()),
        "type": "system",
        "level": "info",
        "title": "Knowledge Base Updated",
        "message": "Ingested 12 new data points from Fed minutes and earnings reports.",
        "action_required": False,
        "action_url": "/knowledge",
        "dismissed": False,
        "created_at": (_now - timedelta(hours=4)).isoformat() + "Z",
    },
    {
        "id": str(uuid4()),
        "type": "trade",
        "level": "warning",
        "title": "Stop Loss Approaching",
        "message": "SPY short position approaching stop loss at $510.00 (current: $511.85).",
        "action_required": False,
        "action_url": "/trades",
        "dismissed": False,
        "created_at": (_now - timedelta(hours=6)).isoformat() + "Z",
    },
]
for a in _seed_alerts:
    _alerts_store[a["id"]] = a


@router.get("/", response_model=list[AlertResponse])
async def list_alerts(
    type: str | None = Query(None, description="Filter by type"),
    level: str | None = Query(None, description="Filter by level"),
    dismissed: bool | None = Query(None, description="Filter by dismissed status"),
):
    """List all alerts with optional filters."""
    results = list(_alerts_store.values())

    if type:
        results = [a for a in results if a["type"] == type]
    if level:
        results = [a for a in results if a["level"] == level]
    if dismissed is not None:
        results = [a for a in results if a["dismissed"] == dismissed]

    results.sort(key=lambda a: a["created_at"], reverse=True)
    return [AlertResponse(**a) for a in results]


@router.post("/{alert_id}/dismiss", response_model=DismissResponse)
async def dismiss_alert(alert_id: str):
    """Dismiss a specific alert."""
    alert = _alerts_store.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    alert["dismissed"] = True
    return DismissResponse(id=alert_id, dismissed=True, message="Alert dismissed")


@router.post("/dismiss-all", response_model=dict)
async def dismiss_all_alerts():
    """Dismiss all alerts."""
    count = 0
    for alert in _alerts_store.values():
        if not alert["dismissed"]:
            alert["dismissed"] = True
            count += 1
    return {"dismissed_count": count, "message": f"Dismissed {count} alerts"}
