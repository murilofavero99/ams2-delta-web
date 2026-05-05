"""
API endpoints para sessões.

GET /sessions - lista todas
GET /sessions/{id} - detalhes de uma sessão
GET /sessions/{id}/laps/{lap}/telemetry - telemetria de uma volta
"""
import sqlite3
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query, UploadFile, File

from ..db import supabase_client, supabase_repo
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

print(f"[i] Sessions directory: {SESSIONS_DIR} (exists: {SESSIONS_DIR.exists()})")


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

    Comportamento:
      - Se Supabase configurado: parseia o session.db, joga metadata+laps no
        Postgres e o telemetry.parquet no Storage.
      - Senão: grava em disco (modo legacy).
    """
    import re
    if not re.match(r'^[a-zA-Z0-9_\-]+$', session_id):
        raise HTTPException(status_code=400, detail="session_id inválido")

    db_content = await session_db.read()
    parquet_content = await telemetry.read()

    # ─── Modo Supabase ──────────────────────────────────────────────────
    if supabase_client.is_enabled():
        try:
            metadata, laps = _parse_session_db(db_content, session_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"session.db inválido: {e}")

        ok_db = supabase_repo.upsert_session(metadata, laps)
        ok_storage = supabase_repo.upload_telemetry_bytes(session_id, parquet_content)
        if not (ok_db and ok_storage):
            raise HTTPException(status_code=500, detail="Falha ao gravar no Supabase")

        return {
            "status": "ok",
            "backend": "supabase",
            "session_id": session_id,
            "db_size": len(db_content),
            "parquet_size": len(parquet_content),
            "num_laps": len(laps),
        }

    # ─── Modo disco (legacy) ────────────────────────────────────────────
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "session.db").write_bytes(db_content)
    (session_dir / "telemetry.parquet").write_bytes(parquet_content)

    global session_service
    session_service = SessionService(SESSIONS_DIR)

    return {
        "status": "ok",
        "backend": "disk",
        "session_id": session_id,
        "db_size": len(db_content),
        "parquet_size": len(parquet_content),
    }


def _parse_session_db(db_bytes: bytes, session_id: str) -> tuple[dict, list[dict]]:
    """
    Lê o conteúdo binário de um session.db SQLite e extrai (metadata, laps)
    em formato pronto pra inserir no Postgres.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(db_bytes)
        tmp_path = tmp.name

    try:
        conn = sqlite3.connect(tmp_path)
        info = dict(conn.execute("SELECT key, value FROM session_info").fetchall())
        lap_rows = conn.execute(
            "SELECT lap_number, lap_time_s, sector1_s, sector2_s, sector3_s, invalidated FROM laps"
        ).fetchall()
        conn.close()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    metadata = {
        "session_id": info.get("session_id", session_id),
        "started_at": info.get("started_at", ""),
        "track_location": info.get("track_location", "unknown") or "unknown",
        "track_variation": info.get("track_variation", "") or "",
        "track_length_m": float(info.get("track_length_m", 0.0) or 0.0),
        "num_samples": int(info.get("num_samples", 0) or 0),
        "num_laps": int(info.get("num_laps", 0) or 0),
        "car_name": info.get("car_name", "") or "",
        "car_class_name": info.get("car_class_name", "") or "",
        "car_class_id": int(info.get("car_class_id", 0) or 0),
        "telemetry_path": f"{session_id}/telemetry.parquet",
    }

    laps = [
        {
            "session_id": session_id,
            "lap_number": int(n),
            "lap_time_s": float(t) if t is not None else None,
            "sector1_s": float(s1) if s1 is not None else None,
            "sector2_s": float(s2) if s2 is not None else None,
            "sector3_s": float(s3) if s3 is not None else None,
            "invalidated": int(inv or 0),
        }
        for (n, t, s1, s2, s3, inv) in lap_rows
    ]
    return metadata, laps
