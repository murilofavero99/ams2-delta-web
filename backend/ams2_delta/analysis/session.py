"""
Análise pós-sessão: carrega dados gravados e fornece funções para comparar voltas.

Conceito-chave do Delta:
    Para comparar duas voltas de forma justa, não dá pra alinhá-las por tempo
    (se uma é mais rápida, o "mesmo instante" aponta pontos diferentes da pista).
    A forma correta é alinhar por DISTÂNCIA PERCORRIDA NA VOLTA.

    Para cada volta, re-amostramos os traços (speed, throttle, brake, etc.) numa
    grade fixa de distância (ex.: 0m, 1m, 2m, ..., track_length). Aí, para um
    dado ponto da pista, temos os valores de ambas as voltas alinhados.

    O DELTA acumulado em cada ponto é a diferença entre:
        - o tempo que a volta A gastou pra chegar até aquela distância
        - o tempo que a volta B (referência) gastou pra chegar até aquela distância

    Delta positivo = volta A está perdendo tempo vs B nesse ponto.
    Delta negativo = volta A está ganhando.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Carregamento de sessão
# ----------------------------------------------------------------------------

@dataclass
class SessionMetadata:
    session_id: str
    started_at: str
    track_location: str
    track_variation: str
    track_length_m: float
    num_samples: int
    num_laps: int
    car_name: str = ""
    car_class_name: str = ""


@dataclass
class LapRecord:
    lap_number: int
    lap_time_s: float
    sector1_s: Optional[float]
    sector2_s: Optional[float]
    sector3_s: Optional[float]
    invalidated: bool


@dataclass
class Session:
    metadata: SessionMetadata
    laps: list[LapRecord]
    telemetry: pd.DataFrame   # todos os samples, com coluna current_lap

    def lap_telemetry(self, lap_number: int) -> pd.DataFrame:
        """
        Retorna os samples de uma volta específica, ordenados por tempo.
        
        Se houve instant reset durante a volta (Time Trial), retorna
        apenas o ÚLTIMO segmento completo — que é a tentativa válida.
        """
        from .lap_validation import get_best_segment
        df = self.telemetry[self.telemetry["current_lap"] == lap_number].copy()
        df = df.sort_values("wall_time").reset_index(drop=True)
        if len(df) < 10:
            return df
        return get_best_segment(df, self.metadata.track_length_m)

    def valid_laps(self) -> list[LapRecord]:
        """Só voltas não invalidadas, com tempo > 0, e que cruzaram a linha de chegada."""
        from .lap_validation import is_lap_complete
        
        valid = []
        for lap in self.laps:
            if lap.invalidated or lap.lap_time_s <= 0:
                continue
            
            # Verifica se a volta foi completa (cruzou linha de chegada)
            lap_df = self.lap_telemetry(lap.lap_number)
            if is_lap_complete(lap_df, self.metadata.track_length_m, tolerance_m=100.0):
                valid.append(lap)
        
        return valid

    def fastest_lap(self) -> Optional[LapRecord]:
        valid = self.valid_laps()
        if not valid:
            return None
        return min(valid, key=lambda l: l.lap_time_s)


def list_sessions(sessions_dir: Path) -> list[Path]:
    """Lista diretórios de sessão válidos (que têm session.db)."""
    if not sessions_dir.exists():
        return []
    dirs = [p for p in sessions_dir.iterdir()
            if p.is_dir() and (p / "session.db").exists()]
    return sorted(dirs, reverse=True)  # mais recente primeiro


def load_session(session_dir: Path) -> Session:
    """Carrega metadata (SQLite) + telemetria (Parquet) de uma sessão."""
    db_path = session_dir / "session.db"
    parquet_path = session_dir / "telemetry.parquet"

    if not db_path.exists():
        raise FileNotFoundError(f"session.db não encontrado em {session_dir}")

    # Metadata
    conn = sqlite3.connect(db_path)
    info_rows = dict(conn.execute("SELECT key, value FROM session_info").fetchall())

    metadata = SessionMetadata(
        session_id=info_rows.get("session_id", session_dir.name),
        started_at=info_rows.get("started_at", ""),
        track_location=info_rows.get("track_location", "unknown"),
        track_variation=info_rows.get("track_variation", ""),
        track_length_m=float(info_rows.get("track_length_m", 0.0) or 0.0),
        num_samples=int(info_rows.get("num_samples", 0) or 0),
        num_laps=int(info_rows.get("num_laps", 0) or 0),
        car_name=info_rows.get("car_name", "") or "",
        car_class_name=info_rows.get("car_class_name", "") or "",
    )

    # Laps
    lap_rows = conn.execute(
        "SELECT lap_number, lap_time_s, sector1_s, sector2_s, sector3_s, invalidated "
        "FROM laps ORDER BY lap_number"
    ).fetchall()
    laps = [LapRecord(n, t, s1, s2, s3, bool(inv))
            for n, t, s1, s2, s3, inv in lap_rows]
    conn.close()

    # Telemetria
    if parquet_path.exists():
        telemetry = pd.read_parquet(parquet_path)
    else:
        telemetry = pd.DataFrame()

    return Session(metadata=metadata, laps=laps, telemetry=telemetry)


# ----------------------------------------------------------------------------
# Alinhamento por distância
# ----------------------------------------------------------------------------

def resample_lap_by_distance(lap_df: pd.DataFrame,
                             distance_grid: np.ndarray,
                             channels: Optional[list[str]] = None) -> pd.DataFrame:
    """
    Re-amostra uma volta numa grade fixa de distância percorrida.

    Args:
        lap_df: DataFrame com samples de UMA volta. Precisa ter 'current_lap_distance'
                e 'current_time_s'.
        distance_grid: array numpy com as distâncias alvo em metros (ex.: np.arange(0, 4361, 1))
        channels: colunas a re-amostrar. Default: channels úteis pra análise.

    Returns:
        DataFrame com 'distance_m' + cada channel interpolado nessa grade.
    """
    if channels is None:
        channels = ["speed_kmh", "throttle_pct", "brake_pct", "steering_pct",
                    "rpm", "gear", "current_time_s",
                    "accel_local_x", "accel_local_y", "accel_local_z",
                    "world_x", "world_y", "world_z"]

    if len(lap_df) < 2:
        return pd.DataFrame({"distance_m": distance_grid})

    # current_lap_distance precisa ser monotônico (sempre crescente dentro da volta).
    # Pode haver pequenos glitches do jogo — filtramos mantendo só pontos onde
    # a distância de fato cresceu.
    df = lap_df.sort_values("wall_time").reset_index(drop=True)
    dist = df["current_lap_distance"].to_numpy()

    # Mantém apenas índices onde a distância é estritamente crescente
    keep = np.concatenate(([True], np.diff(dist) > 0))
    df = df.loc[keep].reset_index(drop=True)
    dist = df["current_lap_distance"].to_numpy()

    if len(df) < 2:
        return pd.DataFrame({"distance_m": distance_grid})

    out = {"distance_m": distance_grid}
    for ch in channels:
        if ch not in df.columns:
            continue
        values = df[ch].to_numpy(dtype=float)
        # np.interp faz interpolação linear. Valores fora da faixa são cortados
        # no valor da extremidade — aceitável porque a grade vai até track_length.
        out[ch] = np.interp(distance_grid, dist, values)

    return pd.DataFrame(out)


def compute_delta(lap_df: pd.DataFrame, reference_df: pd.DataFrame,
                  track_length_m: Optional[float] = None,
                  step_m: float = 1.0) -> pd.DataFrame:
    """
    Calcula o delta entre uma volta e uma volta de referência, alinhadas por distância.

    Args:
        lap_df: telemetria da volta a analisar (output de session.lap_telemetry())
        reference_df: telemetria da volta de referência
        track_length_m: comprimento da pista. Se None, usa o máximo de current_lap_distance.
        step_m: resolução da grade em metros (1m = alta qualidade, 5m = mais leve)

    Returns:
        DataFrame com colunas:
            distance_m, time_lap_s, time_ref_s, delta_s,
            speed_lap, speed_ref, throttle_lap, throttle_ref, brake_lap, brake_ref
    """
    if lap_df.empty or reference_df.empty:
        return pd.DataFrame()

    if track_length_m is None or track_length_m <= 0:
        track_length_m = float(max(
            lap_df["current_lap_distance"].max(),
            reference_df["current_lap_distance"].max()
        ))

    grid = np.arange(0, track_length_m + step_m, step_m)

    lap_resampled = resample_lap_by_distance(lap_df, grid)
    ref_resampled = resample_lap_by_distance(reference_df, grid)

    if "current_time_s" not in lap_resampled or "current_time_s" not in ref_resampled:
        return pd.DataFrame()

    delta = pd.DataFrame({
        "distance_m": grid,
        "time_lap_s": lap_resampled["current_time_s"],
        "time_ref_s": ref_resampled["current_time_s"],
        "speed_lap": lap_resampled.get("speed_kmh", np.nan),
        "speed_ref": ref_resampled.get("speed_kmh", np.nan),
        "throttle_lap": lap_resampled.get("throttle_pct", np.nan),
        "throttle_ref": ref_resampled.get("throttle_pct", np.nan),
        "brake_lap": lap_resampled.get("brake_pct", np.nan),
        "brake_ref": ref_resampled.get("brake_pct", np.nan),
        "steering_lap": lap_resampled.get("steering_pct", np.nan),
        "steering_ref": ref_resampled.get("steering_pct", np.nan),
        "gear_lap": lap_resampled.get("gear", np.nan),
        "gear_ref": ref_resampled.get("gear", np.nan),
    })
    delta["delta_s"] = delta["time_lap_s"] - delta["time_ref_s"]

    return delta


def summarize_delta(delta_df: pd.DataFrame) -> dict:
    """
    Extrai métricas resumo úteis da análise de delta.
    """
    if delta_df.empty:
        return {}

    final_delta = float(delta_df["delta_s"].iloc[-1])
    max_loss_idx = int(delta_df["delta_s"].idxmax())
    max_gain_idx = int(delta_df["delta_s"].idxmin())

    return {
        "final_delta_s": final_delta,
        "max_loss_s": float(delta_df["delta_s"].iloc[max_loss_idx]),
        "max_loss_at_m": float(delta_df["distance_m"].iloc[max_loss_idx]),
        "max_gain_s": float(delta_df["delta_s"].iloc[max_gain_idx]),
        "max_gain_at_m": float(delta_df["distance_m"].iloc[max_gain_idx]),
        "max_speed_lap_kmh": float(delta_df["speed_lap"].max()),
        "max_speed_ref_kmh": float(delta_df["speed_ref"].max()),
    }


def format_lap_time(seconds: float) -> str:
    if seconds is None or seconds <= 0:
        return "--:--.---"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}"


# ----------------------------------------------------------------------------
# Detecção de zonas de freada
# ----------------------------------------------------------------------------

@dataclass
class BrakingZone:
    """
    Representa uma zona de freada identificada em uma volta.

    O "início" é onde o piloto começou a pisar no freio com intensidade real,
    e o "fim" é onde soltou (ou pressão caiu abaixo do limite).
    """
    index_start: int           # índice no DataFrame onde começou
    index_end: int             # índice onde terminou
    distance_start_m: float    # distância na volta onde começou (metros)
    distance_end_m: float
    duration_m: float          # comprimento da zona de freada em metros
    speed_entry_kmh: float     # velocidade no início (útil pra ver qual curva é)
    speed_exit_kmh: float      # velocidade ao soltar o freio
    max_brake_pct: float       # pico de pressão no freio durante a zona
    world_x_start: float       # posição mundial do início (pro mapa)
    world_z_start: float


def detect_braking_zones(lap_df: pd.DataFrame,
                         threshold_pct: float = 20.0,
                         min_duration_m: float = 15.0) -> list[BrakingZone]:
    """
    Detecta zonas de freada numa volta.

    Uma zona de freada é um trecho contínuo onde brake_pct > threshold_pct.
    Zonas muito curtas (menos que min_duration_m metros) são descartadas
    pra filtrar freadas acidentais e ruído.

    Args:
        lap_df: telemetria de UMA volta, com colunas brake_pct, speed_kmh,
                current_lap_distance, world_x, world_z.
        threshold_pct: intensidade mínima de freio pra contar como "freando"
        min_duration_m: duração mínima em metros pra considerar zona real

    Returns:
        Lista de BrakingZone, ordenada pela ordem na volta.
    """
    if lap_df.empty or "brake_pct" not in lap_df.columns:
        return []

    df = lap_df.sort_values("wall_time").reset_index(drop=True)
    braking = df["brake_pct"].values > threshold_pct

    zones = []
    i = 0
    n = len(df)
    while i < n:
        if not braking[i]:
            i += 1
            continue

        # Começo de uma zona
        start = i
        while i < n and braking[i]:
            i += 1
        end = i - 1

        dist_start = float(df["current_lap_distance"].iloc[start])
        dist_end = float(df["current_lap_distance"].iloc[end])
        duration = dist_end - dist_start

        if duration < min_duration_m:
            continue

        zones.append(BrakingZone(
            index_start=start,
            index_end=end,
            distance_start_m=dist_start,
            distance_end_m=dist_end,
            duration_m=duration,
            speed_entry_kmh=float(df["speed_kmh"].iloc[start]),
            speed_exit_kmh=float(df["speed_kmh"].iloc[end]),
            max_brake_pct=float(df["brake_pct"].iloc[start:end+1].max()),
            world_x_start=float(df["world_x"].iloc[start]),
            world_z_start=float(df["world_z"].iloc[start]),
        ))

    return zones


def compare_braking_points(target_zones: list[BrakingZone],
                           reference_zones: list[BrakingZone],
                           match_tolerance_m: float = 150.0) -> list[dict]:
    """
    Pareia zonas de freada do alvo com as da referência por proximidade
    na pista. Retorna uma lista de dicts com os dados pareados e a diferença
    de ponto de freada (negativa = freou mais cedo, positiva = mais tarde).

    Args:
        target_zones: zonas da volta que está sendo analisada
        reference_zones: zonas da volta de referência
        match_tolerance_m: distância máxima (em m) para considerar zonas "a mesma curva"

    Returns:
        Lista de dicts com chaves: curve_num, ref_distance_m, target_distance_m,
        diff_m (target - ref), speed_entry, etc.
    """
    results = []
    for i, ref_zone in enumerate(reference_zones):
        # Acha a zona alvo mais próxima que ainda não foi usada
        best_match = None
        best_dist = float("inf")
        for target_zone in target_zones:
            d = abs(target_zone.distance_start_m - ref_zone.distance_start_m)
            if d < best_dist and d <= match_tolerance_m:
                best_dist = d
                best_match = target_zone

        if best_match is None:
            continue

        diff_m = best_match.distance_start_m - ref_zone.distance_start_m
        results.append({
            "curve_num": i + 1,
            "ref_distance_m": ref_zone.distance_start_m,
            "target_distance_m": best_match.distance_start_m,
            "diff_m": diff_m,
            "ref_speed_entry": ref_zone.speed_entry_kmh,
            "target_speed_entry": best_match.speed_entry_kmh,
            "ref_max_brake": ref_zone.max_brake_pct,
            "target_max_brake": best_match.max_brake_pct,
            "ref_world_x": ref_zone.world_x_start,
            "ref_world_z": ref_zone.world_z_start,
        })

    return results
