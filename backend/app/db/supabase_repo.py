"""
Repository functions para acessar sessões no Supabase.

Postgres armazena os metadados (sessions + laps).
Supabase Storage armazena os arquivos telemetry.parquet.

Os arquivos parquet baixados são cacheados em disco temporariamente
em $SUPABASE_CACHE_DIR (default: /tmp/ams2_cache) — o cache é
invalidado se o Storage retornar arquivo novo.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from ams2_delta.analysis.session import Session, SessionMetadata, LapRecord

from .supabase_client import get_bucket_name, get_client


_CACHE_DIR = Path(os.environ.get("SUPABASE_CACHE_DIR", Path(tempfile.gettempdir()) / "ams2_cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _telemetry_object_path(session_id: str) -> str:
    """Caminho do parquet dentro do bucket de Storage."""
    return f"{session_id}/telemetry.parquet"


def list_session_ids() -> list[str]:
    """Lista todos os session_ids ordenados por started_at desc."""
    client = get_client()
    if client is None:
        return []
    res = client.table("sessions").select("session_id").order("started_at", desc=True).execute()
    return [row["session_id"] for row in (res.data or [])]


def load_session_metadata(session_id: str) -> Optional[SessionMetadata]:
    client = get_client()
    if client is None:
        return None
    res = client.table("sessions").select("*").eq("session_id", session_id).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return SessionMetadata(
        session_id=row["session_id"],
        started_at=row.get("started_at", "") or "",
        track_location=row.get("track_location", "unknown") or "unknown",
        track_variation=row.get("track_variation", "") or "",
        track_length_m=float(row.get("track_length_m", 0.0) or 0.0),
        num_samples=int(row.get("num_samples", 0) or 0),
        num_laps=int(row.get("num_laps", 0) or 0),
        car_name=row.get("car_name", "") or "",
        car_class_name=row.get("car_class_name", "") or "",
    )


def load_session_laps(session_id: str) -> list[LapRecord]:
    client = get_client()
    if client is None:
        return []
    res = (
        client.table("laps")
        .select("lap_number, lap_time_s, sector1_s, sector2_s, sector3_s, invalidated")
        .eq("session_id", session_id)
        .order("lap_number")
        .execute()
    )
    laps: list[LapRecord] = []
    for row in (res.data or []):
        laps.append(LapRecord(
            lap_number=int(row["lap_number"]),
            lap_time_s=float(row.get("lap_time_s") or 0.0),
            sector1_s=row.get("sector1_s"),
            sector2_s=row.get("sector2_s"),
            sector3_s=row.get("sector3_s"),
            invalidated=bool(row.get("invalidated", 0)),
        ))
    return laps


def download_telemetry(session_id: str, force_refresh: bool = False) -> Optional[Path]:
    """Baixa telemetry.parquet do Storage para um cache local. Retorna o path local."""
    client = get_client()
    if client is None:
        return None

    cache_path = _CACHE_DIR / session_id / "telemetry.parquet"
    if cache_path.exists() and not force_refresh:
        return cache_path

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    bucket = get_bucket_name()
    obj_path = _telemetry_object_path(session_id)

    try:
        data = client.storage.from_(bucket).download(obj_path)
    except Exception as e:
        print(f"[!] Falha ao baixar {obj_path}: {e}")
        return None

    cache_path.write_bytes(data)
    return cache_path


def load_full_session(session_id: str) -> Optional[Session]:
    """Carrega metadata + laps + telemetria (parquet baixado/cacheado)."""
    metadata = load_session_metadata(session_id)
    if metadata is None:
        return None
    laps = load_session_laps(session_id)

    parquet_path = download_telemetry(session_id)
    if parquet_path and parquet_path.exists():
        try:
            telemetry = pd.read_parquet(parquet_path)
        except Exception as e:
            print(f"[!] Falha ao ler parquet de {session_id}: {e}")
            telemetry = pd.DataFrame()
    else:
        telemetry = pd.DataFrame()

    return Session(metadata=metadata, laps=laps, telemetry=telemetry)


def upsert_session(metadata: dict, laps: list[dict]) -> bool:
    """Insere/atualiza uma sessão e suas voltas no Postgres."""
    client = get_client()
    if client is None:
        return False
    try:
        client.table("sessions").upsert(metadata).execute()
        if laps:
            # apaga voltas antigas e reinsere (mais simples que diff)
            client.table("laps").delete().eq("session_id", metadata["session_id"]).execute()
            client.table("laps").insert(laps).execute()
        return True
    except Exception as e:
        print(f"[!] Falha ao upsert sessão {metadata.get('session_id')}: {e}")
        return False


def upload_telemetry_bytes(session_id: str, parquet_bytes: bytes) -> bool:
    """Sobe o parquet para o bucket de Storage (faz upsert)."""
    client = get_client()
    if client is None:
        return False
    bucket = get_bucket_name()
    obj_path = _telemetry_object_path(session_id)
    try:
        # upsert via remove + upload (a API do supabase-py varia entre versões;
        # esta forma é a mais compatível)
        try:
            client.storage.from_(bucket).remove([obj_path])
        except Exception:
            pass
        client.storage.from_(bucket).upload(
            path=obj_path,
            file=parquet_bytes,
            file_options={"content-type": "application/octet-stream"},
        )
        return True
    except Exception as e:
        print(f"[!] Falha ao subir parquet de {session_id}: {e}")
        return False
