"""
Service para gerenciar sessões gravadas.

Reutiliza o código de análise do ams2_delta original.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Adiciona o código original ao path
SHARED_PATH = Path(__file__).resolve().parents[3] / "shared"
if str(SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(SHARED_PATH))

from ams2_delta.analysis.session import Session, load_session, list_sessions
from ams2_delta.analysis.lap_validation import (
    get_best_segment, is_lap_complete, lap_completeness_stats,
)

from ..models.schemas import (
    LapSummary, SessionMetadata, SessionResponse, TelemetryPoint,
)


class SessionService:
    """Gerencia acesso a sessões gravadas."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir

    def list_all(self) -> list[SessionResponse]:
        """Lista todas as sessões disponíveis."""
        session_dirs = list_sessions(self.sessions_dir)
        results = []

        for session_dir in session_dirs:
            try:
                session = load_session(session_dir)
                results.append(self._session_to_response(session))
            except Exception as e:
                print(f"Erro ao carregar {session_dir}: {e}")
                continue

        return sorted(results, key=lambda s: s.metadata.started_at, reverse=True)

    def get_by_id(self, session_id: str) -> Optional[SessionResponse]:
        """Retorna uma sessão específica por ID."""
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return None

        session = load_session(session_dir)
        return self._session_to_response(session)

    def get_lap_telemetry(self, session_id: str, lap_number: int,
                          max_points: int = 5000) -> list[TelemetryPoint]:
        """
        Retorna telemetria de uma volta específica.

        Args:
            max_points: limita número de pontos (downsampling pra mobile)
        """
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return []

        session = load_session(session_dir)
        lap_df = session.lap_telemetry(lap_number)

        if lap_df.empty:
            return []

        # Downsample se necessário (pra não explodir mobile com 20k pontos)
        df_list = lap_df.to_dict(orient='records')
        if len(df_list) > max_points:
            step = len(df_list) // max_points
            df_list = df_list[::step]

        # Converte -> list[TelemetryPoint]
        points = []
        for row in df_list:
            points.append(TelemetryPoint(
                wall_time=row["wall_time"],
                current_lap=row["current_lap"],
                current_lap_distance=row["current_lap_distance"],
                current_time_s=row["current_time_s"],
                speed_kmh=row["speed_kmh"],
                rpm=row["rpm"],
                gear=row["gear"],
                throttle_pct=row["throttle_pct"],
                brake_pct=row["brake_pct"],
                steering_pct=row["steering_pct"],
                world_x=row["world_x"],
                world_z=row["world_z"],
            ))

        return points

    def _session_to_response(self, session: Session) -> SessionResponse:
        """Converte Session interna -> SessionResponse (JSON)."""
        valid_laps = session.valid_laps()
        fastest = session.fastest_lap()

        laps_summary = []
        for lap in valid_laps:
            lap_df = session.lap_telemetry(lap.lap_number)
            stats = lap_completeness_stats(lap_df, session.metadata.track_length_m)

            laps_summary.append(LapSummary(
                lap_number=lap.lap_number,
                lap_time_s=lap.lap_time_s,
                invalidated=lap.invalidated,
                is_fastest=(fastest and lap.lap_number == fastest.lap_number),
                completeness_pct=stats["completeness_pct"],
                num_resets=stats.get("num_resets", 0),
            ))

        return SessionResponse(
            metadata=SessionMetadata(
                session_id=session.metadata.session_id,
                started_at=session.metadata.started_at,
                track_location=session.metadata.track_location,
                track_variation=session.metadata.track_variation,
                track_length_m=session.metadata.track_length_m,
                num_samples=session.metadata.num_samples,
                num_laps=session.metadata.num_laps,
            ),
            laps=laps_summary,
        )
