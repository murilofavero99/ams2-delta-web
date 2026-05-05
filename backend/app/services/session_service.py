"""
Service para gerenciar sessões gravadas.

Modo dual:
  - Se SUPABASE_URL + SUPABASE_KEY estão setadas → lê do Supabase
  - Senão → lê de disco (modo legacy, requer sessions_dir)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ams2_delta.analysis.session import Session, load_session, list_sessions
from ams2_delta.analysis.lap_validation import (
    get_best_segment, is_lap_complete, lap_completeness_stats,
)

from ..db import supabase_client, supabase_repo
from ..models.schemas import (
    LapSummary, SessionMetadata, SessionResponse, TelemetryPoint,
)


class SessionService:
    """Gerencia acesso a sessões gravadas (Supabase ou disco)."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir

    # ------------------------------------------------------------------ public

    def list_all(self) -> list[SessionResponse]:
        if supabase_client.is_enabled():
            return self._list_all_supabase()
        return self._list_all_disk()

    def get_by_id(self, session_id: str) -> Optional[SessionResponse]:
        if supabase_client.is_enabled():
            session = supabase_repo.load_full_session(session_id)
            if session is None:
                return None
            return self._session_to_response(session)
        return self._get_by_id_disk(session_id)

    def get_lap_telemetry(self, session_id: str, lap_number: int,
                          max_points: int = 5000) -> list[TelemetryPoint]:
        if supabase_client.is_enabled():
            session = supabase_repo.load_full_session(session_id)
        else:
            session_dir = self.sessions_dir / session_id
            if not session_dir.exists():
                return []
            session = load_session(session_dir)

        if session is None:
            return []
        lap_df = session.lap_telemetry(lap_number)
        if lap_df.empty:
            return []

        df_list = lap_df.to_dict(orient='records')
        if len(df_list) > max_points:
            step = len(df_list) // max_points
            df_list = df_list[::step]

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

    # ------------------------------------------------------------------ supabase

    def _list_all_supabase(self) -> list[SessionResponse]:
        results: list[SessionResponse] = []
        for sid in supabase_repo.list_session_ids():
            try:
                session = supabase_repo.load_full_session(sid)
                if session is None:
                    continue
                results.append(self._session_to_response(session))
            except Exception as e:
                print(f"Erro ao carregar {sid} do Supabase: {e}")
                continue
        return sorted(results, key=lambda s: s.metadata.started_at, reverse=True)

    # ------------------------------------------------------------------ disco

    def _list_all_disk(self) -> list[SessionResponse]:
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

    def _get_by_id_disk(self, session_id: str) -> Optional[SessionResponse]:
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return None
        session = load_session(session_dir)
        return self._session_to_response(session)

    # ------------------------------------------------------------------ helpers

    def _session_to_response(self, session: Session) -> SessionResponse:
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
                car_name=getattr(session.metadata, "car_name", "") or "",
                car_class_name=getattr(session.metadata, "car_class_name", "") or "",
            ),
            laps=laps_summary,
        )
