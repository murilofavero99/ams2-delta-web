"""
API endpoints para sessões.

GET /sessions - lista todas
GET /sessions/{id} - detalhes de uma sessão
GET /sessions/{id}/laps/{lap}/telemetry - telemetria de uma volta
"""
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query, UploadFile, File

from ..models.schemas import SessionResponse, TelemetryPoint
from ..services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Caminho para as sessões — prioridade:
#   1. Variável de ambiente SESSIONS_DIR (Railway volume mount)
#   2. /app/sessions (Railway default mount path)
#   3. Relativo ao backend (local dev)
#   4. Fallback: cwd/sessions
import os

_env_dir = os.environ.get("SESSIONS_DIR")
if _env_dir and Path(_env_dir).exists():
    SESSIONS_DIR = Path(_env_dir)
elif Path("/app/sessions").exists():
    SESSIONS_DIR = Path("/app/sessions")
else:
    SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
    if not SESSIONS_DIR.exists():
        SESSIONS_DIR = Path("sessions").resolve()

# Cria a pasta se não existir (necessário no primeiro deploy do Railway)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
session_service = SessionService(SESSIONS_DIR)

print(f"📂 Sessions directory: {SESSIONS_DIR} (exists: {SESSIONS_DIR.exists()})")


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


@router.post("/upload")
async def upload_session(
    session_db: UploadFile = File(...),
    telemetry: UploadFile = File(...),
    session_id: str = Query(..., description="ID da sessão (nome da pasta)"),
):
    """
    Upload de uma sessão (session.db + telemetry.parquet).

    Permite subir sessões gravadas localmente para o servidor cloud.
    """
    import re
    # Valida session_id (segurança)
    if not re.match(r'^[a-zA-Z0-9_\-]+$', session_id):
        raise HTTPException(status_code=400, detail="session_id inválido")

    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Salva session.db
    db_path = session_dir / "session.db"
    db_content = await session_db.read()
    db_path.write_bytes(db_content)

    # Salva telemetry.parquet
    parquet_path = session_dir / "telemetry.parquet"
    parquet_content = await telemetry.read()
    parquet_path.write_bytes(parquet_content)

    # Recarrega o service pra pegar a nova sessão
    global session_service
    session_service = SessionService(SESSIONS_DIR)

    return {
        "status": "ok",
        "session_id": session_id,
        "db_size": len(db_content),
        "parquet_size": len(parquet_content),
    }
