"""
Detector de completude de volta.

Analisa a telemetria pra identificar:
- Voltas completas (cruzou linha de chegada)
- Voltas incompletas (bateu, resetou, ou saiu da pista)
- Voltas com instant reset no meio (Time Trial)

Caso especial do Time Trial:
    Quando o piloto usa "instant reset", o AMS2 reinicia current_lap_distance
    pra 0 mas NÃO incrementa current_lap. Resultado: a telemetria de uma
    "volta" pode ter múltiplos segmentos (cada reset = novo segmento).
    O detector identifica esses segmentos e mantém apenas o último completo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def split_by_resets(lap_df: pd.DataFrame,
                    reset_threshold_m: float = 200.0) -> list[pd.DataFrame]:
    """
    Divide a telemetria de uma volta em segmentos separados por instant reset.

    Um "instant reset" é detectado quando current_lap_distance cai
    abruptamente (ex.: de 2500m pra 50m = reset).

    Returns:
        Lista de DataFrames, um por segmento. O último é a tentativa mais recente.
    """
    if lap_df.empty:
        return [lap_df]

    df = lap_df.sort_values("wall_time").reset_index(drop=True)
    distance = df["current_lap_distance"].values
    diffs = np.diff(distance)

    # Encontra os índices onde houve reset (queda grande)
    reset_indices = np.where(diffs < -reset_threshold_m)[0] + 1

    if len(reset_indices) == 0:
        return [df]

    # Divide em segmentos
    segments = []
    start = 0
    for reset_idx in reset_indices:
        segment = df.iloc[start:reset_idx].copy()
        if len(segment) > 5:
            segments.append(segment)
        start = reset_idx

    # Último segmento (após o último reset)
    last_segment = df.iloc[start:].copy()
    if len(last_segment) > 5:
        segments.append(last_segment)

    return segments if segments else [df]


def is_lap_complete(lap_df: pd.DataFrame, track_length_m: float,
                    tolerance_m: float = 100.0) -> bool:
    """
    Detecta se uma volta foi COMPLETA (cruzou a linha de chegada).

    Suporta instant reset do Time Trial: analisa o ÚLTIMO segmento da volta
    (após o último reset) pra verificar se foi completo.

    Returns:
        True se o último segmento foi completo, False caso contrário
    """
    if lap_df.empty or len(lap_df) < 10:
        return False

    # Pega o último segmento (após qualquer instant reset)
    segments = split_by_resets(lap_df, reset_threshold_m=tolerance_m * 2)
    last_segment = segments[-1]
    distance = last_segment["current_lap_distance"].values

    # Verifica se começou perto de 0
    if distance[0] > tolerance_m:
        return False

    # Verifica se alcançou pelo menos 80% da pista
    max_distance = distance.max()
    if track_length_m > 0 and max_distance < track_length_m * 0.8:
        return False

    return True


def get_best_segment(lap_df: pd.DataFrame, track_length_m: float,
                     tolerance_m: float = 100.0) -> pd.DataFrame:
    """
    Retorna o MELHOR segmento de uma volta (o último completo após resets).

    Esse é o dado que deve ser usado pra análise — não a volta inteira
    que pode conter múltiplos resets.
    """
    segments = split_by_resets(lap_df, reset_threshold_m=tolerance_m * 2)

    # Tenta o último segmento primeiro (mais recente)
    for segment in reversed(segments):
        distance = segment["current_lap_distance"].values
        if len(distance) < 10:
            continue
        max_distance = distance.max()
        if track_length_m <= 0 or max_distance >= track_length_m * 0.8:
            return segment

    # Fallback: retorna o maior segmento
    return max(segments, key=len)


def filter_valid_laps(session_df: pd.DataFrame, track_length_m: float,
                      tolerance_m: float = 100.0) -> pd.DataFrame:
    """Filtra o DataFrame completo pra manter APENAS voltas válidas/completas."""
    if session_df.empty or track_length_m <= 0:
        return session_df

    valid_indices = []
    for lap_num in session_df["current_lap"].unique():
        if lap_num < 1:
            continue
        lap_df = session_df[session_df["current_lap"] == lap_num]
        if is_lap_complete(lap_df, track_length_m, tolerance_m):
            valid_indices.extend(lap_df.index)

    return session_df.loc[valid_indices].copy()


def get_valid_lap_numbers(session_df: pd.DataFrame, track_length_m: float,
                          tolerance_m: float = 100.0) -> list[int]:
    """Retorna a lista de números de volta que são válidas."""
    valid_laps = []
    for lap_num in sorted(session_df["current_lap"].unique()):
        if lap_num < 1:
            continue
        lap_df = session_df[session_df["current_lap"] == lap_num]
        if is_lap_complete(lap_df, track_length_m, tolerance_m):
            valid_laps.append(lap_num)
    return valid_laps


def lap_completeness_stats(lap_df: pd.DataFrame, track_length_m: float) -> dict:
    """Retorna estatísticas sobre a completude de uma volta."""
    if lap_df.empty:
        return {"completeness_pct": 0, "reason": "sem dados", "num_resets": 0}

    segments = split_by_resets(lap_df)
    last_segment = segments[-1]
    distance = last_segment["current_lap_distance"].values
    max_distance = distance.max()
    completeness = (max_distance / track_length_m * 100) if track_length_m > 0 else 100.0
    num_resets = len(segments) - 1

    if completeness < 20:
        reason = "Bateu/saiu da pista muito cedo"
    elif completeness < 80:
        reason = f"Incompleta — apenas {completeness:.0f}% da pista"
    else:
        reason = "Completa" if num_resets == 0 else f"Completa (após {num_resets} reset{'s' if num_resets > 1 else ''})"

    return {
        "completeness_pct": completeness,
        "max_distance_m": max_distance,
        "reason": reason,
        "num_resets": num_resets,
    }
