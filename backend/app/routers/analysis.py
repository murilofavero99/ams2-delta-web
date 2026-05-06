"""
API endpoints para análise.

POST /analysis/ai - análise com IA
GET /analysis/{session_id}/delta/{lap1}/{lap2} - delta entre voltas
"""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import AnalysisRequest, AnalysisResponse, CurveInfo, DeltaSummary, TelemetryPoint
from ..services.analysis_service import AnalysisService
from ..services.ideal_lap_service import IdealLapService

router = APIRouter(prefix="/analysis", tags=["analysis"])

SESSIONS_DIR = Path("sessions").resolve()
analysis_service = AnalysisService(SESSIONS_DIR)
ideal_lap_service = IdealLapService(SESSIONS_DIR)


@router.post("/ai", response_model=AnalysisResponse)
async def analyze_with_ai(session_id: str, request: AnalysisRequest):
    """
    Analisa uma volta com IA (Ollama ou Claude).

    Body:
    {
      "lap_number": 1,
      "ai_model": "ollama" | "claude-sonnet" | "claude-opus",
      "api_key": "sk-..." (só pra Claude)
    }
    """
    try:
        return await analysis_service.analyze_lap(
            session_id=session_id,
            lap_number=request.lap_number,
            ai_model=request.ai_model,
            api_key=request.api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na análise: {e}")


@router.get("/{session_id}/laps/{lap_number}/ideal-telemetry",
            response_model=List[TelemetryPoint])
async def get_ideal_lap_telemetry(
    session_id: str,
    lap_number: int,
    max_points: int = Query(default=3000, ge=100, le=10000),
):
    """
    Gera telemetria de uma "volta ideal" sintética sobre a volta indicada.

    Algoritmo determinístico (sem IA): usa as curvas detectadas e a
    velocidade ideal teórica (física GT3) pra construir o perfil de
    speed/brake/throttle que o piloto deveria buscar. Eixo de distância
    e world_x/world_z são preservados pra alinhar a sobreposição.
    """
    try:
        return ideal_lap_service.generate(session_id, lap_number, max_points)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar volta ideal: {e}")


@router.get("/{session_id}/delta/{lap1}/{lap2}")
async def get_delta(session_id: str, lap1: int, lap2: int):
    """
    Calcula delta entre duas voltas.

    Retorna array de pontos com delta acumulado por distância.
    """
    try:
        return analysis_service.compute_delta_between_laps(session_id, lap1, lap2)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
