"""
Detecção automática de curvas a partir de telemetria.

Uma "curva" é identificada por:
- Mudança significativa de velocidade (freada ou aceleração)
- Mudança de steering (giroscópio ativo)
- Duração mínima

O nome é gerado automaticamente: "Curva X", "Chicane X", "Reta X", etc.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Curve:
    """Representa uma curva detectada na volta."""
    curve_num: int              # 1, 2, 3, ...
    curve_type: str             # "Curva", "Chicane", "Reta", "Complexa"
    name: str                   # "Curva 1", "Chicane 2", etc.
    index_start: int            # índice no DataFrame
    index_end: int
    distance_start_m: float     # em que distância da volta começou
    distance_end_m: float
    speed_entry_kmh: float      # velocidade na entrada
    speed_apex_kmh: float       # velocidade no ápice (mais lenta)
    speed_exit_kmh: float       # velocidade na saída
    max_steering_pct: float     # quanto ele girou (0-100)
    avg_brake_pct: float
    avg_throttle_pct: float
    duration_m: float           # quantos metros tem a curva


def detect_curves(lap_df: pd.DataFrame,
                  min_curve_duration_m: float = 20.0,
                  speed_change_threshold_kmh: float = 15.0) -> list[Curve]:
    """
    Detecta curvas na volta analisando mudanças de velocidade e steering.

    Uma curva é identificada quando:
    1. Há uma freada significativa (velocidade cai > threshold)
    2. Steering está ativo (girar volante)
    3. Dura pelo menos min_curve_duration_m metros

    Tipos de curva detectados:
    - "Reta": velocidade mantida, steering mínimo
    - "Curva": mudança de velocidade + steering
    - "Chicane": múltiplas mudanças rápidas de direção
    - "Complexa": padrão de freada + curva + aceleração
    """
    if lap_df.empty or len(lap_df) < 10:
        return []

    df = lap_df.sort_values("wall_time").reset_index(drop=True)

    curves = []
    in_curve = False
    curve_start = 0
    curve_type = None

    for i in range(1, len(df)):
        speed_current = df["speed_kmh"].iloc[i]
        speed_prev = df["speed_kmh"].iloc[i - 1]
        speed_change = abs(speed_current - speed_prev)

        steering = abs(df["steering_pct"].iloc[i])
        brake = df["brake_pct"].iloc[i]

        # Detecta se estamos em uma curva
        is_curving = steering > 10  # giroscópio ativo
        is_braking = brake > 15
        is_accelerating = (speed_current > speed_prev) and (speed_change > 5)

        # Lógica de detecção
        if not in_curve:
            # Inicia uma curva se houver freada + steering ou só steering forte
            if (is_braking and is_curving) or (steering > 30):
                in_curve = True
                curve_start = i
                curve_type = "Curva"  # padrão, depois refina
        else:
            # Termina a curva se voltarmos à reta (steering baixo + velocidade estável)
            if steering < 5 and not is_braking and speed_change < 3:
                # Calcula estatísticas da curva
                curve_df = df.iloc[curve_start:i]
                curve_duration_m = (
                    curve_df["current_lap_distance"].max() -
                    curve_df["current_lap_distance"].min()
                )

                if curve_duration_m >= min_curve_duration_m:
                    # Refina o tipo de curva
                    num_steering_changes = len(
                        curve_df[curve_df["steering_pct"].abs().diff().abs() > 15]
                    )
                    curve_type = (
                        "Chicane" if num_steering_changes >= 2 else
                        "Curva" if curve_df["brake_pct"].mean() > 20 else
                        "Reta"
                    )

                    curves.append(Curve(
                        curve_num=len(curves) + 1,
                        curve_type=curve_type,
                        name=f"{curve_type} {len(curves) + 1}",
                        index_start=curve_start,
                        index_end=i,
                        distance_start_m=curve_df["current_lap_distance"].min(),
                        distance_end_m=curve_df["current_lap_distance"].max(),
                        speed_entry_kmh=curve_df["speed_kmh"].iloc[0],
                        speed_apex_kmh=curve_df["speed_kmh"].min(),
                        speed_exit_kmh=curve_df["speed_kmh"].iloc[-1],
                        max_steering_pct=curve_df["steering_pct"].abs().max(),
                        avg_brake_pct=curve_df["brake_pct"].mean(),
                        avg_throttle_pct=curve_df["throttle_pct"].mean(),
                        duration_m=curve_duration_m,
                    ))

                in_curve = False

    # Se ainda estamos em uma curva no final, fecha ela
    if in_curve:
        curve_df = df.iloc[curve_start:]
        curve_duration_m = (
            curve_df["current_lap_distance"].max() -
            curve_df["current_lap_distance"].min()
        )
        if curve_duration_m >= min_curve_duration_m:
            curves.append(Curve(
                curve_num=len(curves) + 1,
                curve_type=curve_type or "Curva",
                name=f"{curve_type or 'Curva'} {len(curves) + 1}",
                index_start=curve_start,
                index_end=len(df) - 1,
                distance_start_m=curve_df["current_lap_distance"].min(),
                distance_end_m=curve_df["current_lap_distance"].max(),
                speed_entry_kmh=curve_df["speed_kmh"].iloc[0],
                speed_apex_kmh=curve_df["speed_kmh"].min(),
                speed_exit_kmh=curve_df["speed_kmh"].iloc[-1],
                max_steering_pct=curve_df["steering_pct"].abs().max(),
                avg_brake_pct=curve_df["brake_pct"].mean(),
                avg_throttle_pct=curve_df["throttle_pct"].mean(),
                duration_m=curve_duration_m,
            ))

    return curves


def estimate_ideal_speed(curve: Curve,
                         max_lateral_g: float = 1.4,
                         gravity: float = 9.81) -> dict:
    """
    Estima a velocidade ideal teórica para uma curva usando física de racing.

    Baseado em:
    - Raio aproximado da curva (estimado pela steering)
    - Máximo de G lateral que um GT3 aguenta (~1.4G em pneus de corrida)
    - Margem de segurança

    Retorna dict com:
    - ideal_speed_apex: velocidade ideal no ápice da curva
    - margin_kmh: quanto seu speed_apex está abaixo do ideal
    - recommendation: "mantém velocidade" ou "tira mais velocidade"
    """
    # Estimativa de raio (quanto maior steering, mais fechada a curva)
    # steering 30° ≈ raio ~100m, steering 60° ≈ raio ~50m
    steering_rad = np.radians(min(curve.max_steering_pct / 100 * 90, 70))
    estimated_radius_m = 500 / (1 + steering_rad * 10)  # heurística, não é exato

    # Velocidade máxima segura baseada em G-force lateral
    # v_max = sqrt(lateral_g * gravity * radius)
    ideal_speed_mps = np.sqrt(max_lateral_g * gravity * estimated_radius_m)
    ideal_speed_kmh = ideal_speed_mps * 3.6

    # Margem: quanto você está abaixo
    margin = ideal_speed_kmh - curve.speed_apex_kmh

    recommendation = (
        "Tira mais velocidade — curva muito fechada" if margin < -10 else
        "Mantém a velocidade — está no limite" if margin < 5 else
        "Pode entrar mais rápido — tem margem" if margin < 15 else
        "Entra muito lento — perdes 0.5s+ aqui"
    )

    return {
        "ideal_speed_apex_kmh": ideal_speed_kmh,
        "your_speed_apex_kmh": curve.speed_apex_kmh,
        "margin_kmh": margin,
        "recommendation": recommendation,
        "estimated_radius_m": estimated_radius_m,
    }
