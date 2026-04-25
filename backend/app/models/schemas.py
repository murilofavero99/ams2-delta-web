"""
Pydantic models para serialização de dados na API.

Converte os dados internos (SessionState, LapRecord, etc.) em JSON
para o frontend consumir.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SessionMetadata(BaseModel):
    """Metadados de uma sessão gravada."""
    session_id: str
    started_at: str
    track_location: str
    track_variation: str
    track_length_m: float
    num_samples: int
    num_laps: int


class LapSummary(BaseModel):
    """Resumo de uma volta (sem telemetria completa)."""
    lap_number: int
    lap_time_s: float
    invalidated: bool
    is_fastest: bool = False
    completeness_pct: float = 100.0
    num_resets: int = 0


class SessionResponse(BaseModel):
    """Resposta completa de uma sessão."""
    metadata: SessionMetadata
    laps: list[LapSummary]


class TelemetryPoint(BaseModel):
    """Um único sample de telemetria."""
    wall_time: float
    current_lap: int
    current_lap_distance: float
    current_time_s: float
    speed_kmh: float
    rpm: int
    gear: int
    throttle_pct: float
    brake_pct: float
    steering_pct: float
    world_x: float
    world_z: float


class CurveInfo(BaseModel):
    """Informações sobre uma curva detectada."""
    curve_num: int
    name: str
    curve_type: str  # "Curva", "Chicane", "Reta"
    speed_entry_kmh: float
    speed_apex_kmh: float
    speed_exit_kmh: float
    ideal_apex_speed_kmh: float
    speed_margin_kmh: float
    recommendation: str
    max_steering_pct: float
    avg_brake_pct: float
    avg_throttle_pct: float
    duration_m: float


class DeltaSummary(BaseModel):
    """Resumo do delta entre duas voltas."""
    final_delta_s: float
    max_loss_s: float
    max_gain_s: float


class AnalysisRequest(BaseModel):
    """Request para análise com IA."""
    lap_number: int
    ai_model: str = Field(default="ollama", pattern="^(ollama|claude-sonnet|claude-opus)$")
    api_key: Optional[str] = None  # só necessário pra Claude


class AnalysisResponse(BaseModel):
    """Resposta da análise com IA."""
    analysis_text: str
    curves: list[CurveInfo]
    delta_summary: Optional[DeltaSummary] = None
    model_used: str
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
