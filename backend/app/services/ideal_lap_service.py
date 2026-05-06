"""
Service que gera uma "volta ideal" sintética a partir de uma volta real.

Filosofia:
  - Ideal NUNCA é mais lento que o real. Se o piloto já estava no limite
    fisico, o ideal coincide com o real naquele ponto.
  - O ideal mostra OS GANHOS POSSIVEIS — onde o piloto poderia carregar
    mais velocidade no apice, frear mais tarde, ou pisar antes.

Algoritmo (sem IA):
  Para cada curva detectada:
    1. Calcula apex_target = max(real_apex, physics_ideal). Nunca abaixo do real.
    2. Se ganho >= 1 km/h: aplica boost em forma de sino (peak no centro da
       curva, decai nas bordas) numa zona de influencia que se estende
       ~80m antes e depois da curva, capturando a frenagem e a saida.
    3. Brake: na fase de aproximacao (50m antes da curva), reduz brake_pct
       pela metade — sugere frear mais tarde.
    4. Throttle: na saida (ultimos 20m da curva + 50m depois), forca >= 80%
       — sugere pisar antes.
  Retas e curvas onde o piloto ja estava no limite ficam iguais ao real,
  o que faz a comparacao visual ficar honesta.
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


# Quanto antes/depois da curva o "boost" de velocidade espalha (metros).
# Captura a zona de frenagem e o trecho de aceleracao na saida.
INFLUENCE_PRE_M = 80.0
INFLUENCE_POST_M = 80.0
# Quao perto da curva o piloto deveria frear (sugere frear mais tarde).
BRAKE_DELAY_ZONE_M = 50.0
# Quao depois do final da curva o piloto deveria estar a 100% no throttle.
THROTTLE_EARLY_ZONE_M = 50.0
THROTTLE_TARGET_ON_EXIT = 80.0  # %


class IdealLapService:
    """Gera telemetria de volta ideal pra sobreposicao grafica."""

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
            raise ValueError(f"Sessao {session_id} nao encontrada")

        lap_df = session.lap_telemetry(lap_number)
        if lap_df.empty:
            raise ValueError(f"Volta {lap_number} sem telemetria")

        df = lap_df.sort_values("current_lap_distance").reset_index(drop=True)

        curves = detect_curves(df, min_curve_duration_m=20.0)
        curves = label_curves_by_track(
            curves,
            session.metadata.track_location,
            session.metadata.track_variation,
        )

        n = len(df)
        distances = df["current_lap_distance"].astype(float).to_numpy()
        real_speed = df["speed_kmh"].astype(float).to_numpy()
        real_throttle = df["throttle_pct"].astype(float).to_numpy()
        real_brake = df["brake_pct"].astype(float).to_numpy()

        # Comecamos copiando o real — em pontos sem ganho identificado, o ideal
        # vai ser igual ao real (o que e correto: nada a melhorar ali).
        ideal_speed = real_speed.copy()
        ideal_throttle = real_throttle.copy()
        ideal_brake = real_brake.copy()

        for c in curves:
            ideal = estimate_ideal_speed(c)
            physics_apex = float(ideal["ideal_speed_apex_kmh"])

            # Apex nunca abaixo do real (driver pode ter encontrado grip extra)
            apex_target = max(physics_apex, c.speed_apex_kmh)
            gain = apex_target - c.speed_apex_kmh

            if gain < 1.0:
                # piloto ja estava no limite — sem ganho potencial
                continue

            curve_center = (c.distance_start_m + c.distance_end_m) / 2.0
            half_width = max(
                c.distance_end_m - curve_center,
                curve_center - c.distance_start_m,
            )
            # Raio total da zona de influencia (pra normalizar a curva-sino)
            influence_radius = half_width + max(INFLUENCE_PRE_M, INFLUENCE_POST_M)

            # Zona onde aplicamos boost de velocidade
            zone_start = c.distance_start_m - INFLUENCE_PRE_M
            zone_end = c.distance_end_m + INFLUENCE_POST_M
            mask = (distances >= zone_start) & (distances <= zone_end)
            idx = np.where(mask)[0]
            if len(idx) < 3:
                continue

            # Boost em forma de sino: pico no centro, zero nas bordas
            d_in_zone = distances[idx]
            t = np.abs(d_in_zone - curve_center) / influence_radius
            t = np.clip(t, 0.0, 1.0)
            weight = (1.0 - t) ** 2  # decaimento quadratico suave
            boost = gain * weight
            # Adiciona ao real — assim ideal nunca fica abaixo do real
            ideal_speed[idx] = real_speed[idx] + boost

            # ── Frenagem mais tarde ──────────────────────────────────────
            # Nos 50m antes da curva, sugere brake reduzido (= frear mais tarde,
            # nao com menos forca; visualmente o usuario ve "freou cedo demais")
            approach_mask = (
                (distances >= c.distance_start_m - BRAKE_DELAY_ZONE_M)
                & (distances < c.distance_start_m)
            )
            ideal_brake[approach_mask] = real_brake[approach_mask] * 0.4

            # ── Throttle mais cedo na saida ──────────────────────────────
            # Ultimo terco da curva ate 50m apos: throttle minimo de 80%
            exit_zone_start = curve_center  # da metade da curva pra frente
            exit_mask = (
                (distances >= exit_zone_start)
                & (distances <= c.distance_end_m + THROTTLE_EARLY_ZONE_M)
            )
            ideal_throttle[exit_mask] = np.maximum(
                ideal_throttle[exit_mask], THROTTLE_TARGET_ON_EXIT
            )

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
