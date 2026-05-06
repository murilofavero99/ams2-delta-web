"""
Service que gera uma "volta ideal" sintética a partir de uma volta real.

Algoritmo (sem IA, puramente algorítmico):
  1. Detecta curvas na volta real
  2. Para cada curva: substitui velocidade pelo ideal_apex_speed_kmh
     (calculado por física via estimate_ideal_speed)
  3. Constrói perfil V: entry → apex(mínimo) → exit, com brake/throttle
     coerentes (freio antes do ápice, throttle progressivo na saída)
  4. Trechos de reta: força throttle=100, brake=0 (mantém velocidade real
     pra não criar valores absurdos)
  5. Mantém world_x/world_z e current_lap_distance da volta real, pra
     que a sobreposição gráfica fique alinhada por distância

A volta ideal não é fisicamente simulada — é uma referência visual de
"onde a velocidade poderia ser maior nas curvas".
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from ams2_delta.analysis.session import Session, load_session
from ams2_delta.analysis.curve_detection import detect_curves, estimate_ideal_speed
from ams2_delta.analysis.track_curves import label_curves_by_track

from ..db import supabase_client, supabase_repo
from ..models.schemas import TelemetryPoint


class IdealLapService:
    """Gera telemetria de volta ideal pra sobreposição gráfica."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir

    def _load_session(self, session_id: str) -> Optional[Session]:
        if supabase_client.is_enabled():
            return supabase_repo.load_full_session(session_id)
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return None
        return load_session(session_dir)

    def generate(self, session_id: str, lap_number: int,
                 max_points: int = 3000) -> list[TelemetryPoint]:
        session = self._load_session(session_id)
        if session is None:
            raise ValueError(f"Sessão {session_id} não encontrada")

        lap_df = session.lap_telemetry(lap_number)
        if lap_df.empty:
            raise ValueError(f"Volta {lap_number} sem telemetria")

        df = lap_df.sort_values("current_lap_distance").reset_index(drop=True)

        # Detecta curvas
        curves = detect_curves(df, min_curve_duration_m=20.0)
        curves = label_curves_by_track(
            curves,
            session.metadata.track_location,
            session.metadata.track_variation,
        )

        n = len(df)
        ideal_speed = df["speed_kmh"].astype(float).to_numpy().copy()
        ideal_throttle = df["throttle_pct"].astype(float).to_numpy().copy()
        ideal_brake = df["brake_pct"].astype(float).to_numpy().copy()

        distances = df["current_lap_distance"].astype(float).to_numpy()
        in_curve_global = np.zeros(n, dtype=bool)

        for c in curves:
            ideal = estimate_ideal_speed(c)
            apex_target = float(ideal["ideal_speed_apex_kmh"])

            mask = (distances >= c.distance_start_m) & (distances <= c.distance_end_m)
            idx = np.where(mask)[0]
            if len(idx) < 3:
                continue
            in_curve_global[idx] = True

            # Perfil V: entry alta → apex (mínimo) → exit alta
            # Entry/exit garantem que não fica "abaixo" da apex ideal
            entry_v = max(c.speed_entry_kmh, apex_target * 1.35)
            exit_v = max(c.speed_exit_kmh, apex_target * 1.20)

            m = len(idx)
            half = max(1, m // 2)
            for j, k in enumerate(idx):
                if j <= half:
                    t = j / half
                    ideal_speed[k] = entry_v * (1 - t) + apex_target * t
                    # Freio decresce até o ápice; throttle quase nulo
                    ideal_brake[k] = max(0.0, 85.0 * (1 - t))
                    ideal_throttle[k] = 0.0
                else:
                    t = (j - half) / max(1, m - half)
                    ideal_speed[k] = apex_target * (1 - t) + exit_v * t
                    # Saindo do ápice: zero freio, throttle progressivo
                    ideal_brake[k] = 0.0
                    ideal_throttle[k] = min(100.0, 55.0 + 45.0 * t)

        # Em retas: full throttle, zero freio, mantém velocidade real
        # (assume que em reta o piloto já está no limite — foco é otimizar curvas)
        out_mask = ~in_curve_global
        ideal_throttle[out_mask] = 100.0
        ideal_brake[out_mask] = 0.0

        # Downsample
        records = df.to_dict(orient="records")
        if n > max_points:
            step = max(1, n // max_points)
            keep = list(range(0, n, step))
        else:
            keep = list(range(n))

        points: list[TelemetryPoint] = []
        for i in keep:
            row = records[i]
            points.append(TelemetryPoint(
                wall_time=float(row["wall_time"]),
                current_lap=int(row["current_lap"]),
                current_lap_distance=float(row["current_lap_distance"]),
                current_time_s=float(row["current_time_s"]),
                speed_kmh=float(ideal_speed[i]),
                rpm=int(row["rpm"]),
                gear=int(row["gear"]),
                throttle_pct=float(ideal_throttle[i]),
                brake_pct=float(ideal_brake[i]),
                steering_pct=float(row["steering_pct"]),
                world_x=float(row["world_x"]),
                world_z=float(row["world_z"]),
            ))
        return points
