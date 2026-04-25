"""
API endpoints para sessões.

GET /sessions - lista todas
GET /sessions/{id} - detalhes de uma sessão
GET /sessions/{id}/laps/{lap}/telemetry - telemetria de uma volta
"""
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import SessionResponse, TelemetryPoint
from ..services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Caminho para as sessões (ajusta conforme seu setup)
SESSIONS_DIR = Path("sessions").resolve()
session_service = SessionService(SESSIONS_DIR)


@router.get("/", response_model=List[SessionResponse])
async def list_sessions():
    """Lista todas as sessões disponíveis."""
    return session_service.list_all()


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Retorna detalhes de uma sessão específica."""
    session = session_service.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return session


@router.get("/{session_id}/laps/{lap_number}/telemetry",
            response_model=List[TelemetryPoint])
async def get_lap_telemetry(
    session_id: str,
    lap_number: int,
    max_points: int = Query(default=3000, ge=100, le=10000),
):
    """
    Retorna telemetria de uma volta.

    Args:
        max_points: máximo de pontos (downsampling automático pra mobile)
    """
    points = session_service.get_lap_telemetry(session_id, lap_number, max_points)
    if not points:
        raise HTTPException(
            status_code=404,
            detail=f"Volta {lap_number} não encontrada na sessão {session_id}"
        )
    return points
