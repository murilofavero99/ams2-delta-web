"""
Migra sessões existentes (em disco) para o Supabase.

Uso:
    cd backend
    python -m scripts.migrate_to_supabase [--sessions-dir sessions]

Requisitos: env vars SUPABASE_URL e SUPABASE_KEY no shell antes de rodar.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra sessões em disco -> Supabase")
    parser.add_argument("--sessions-dir", default="sessions",
                        help="Pasta com as sessões em disco (default: sessions)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Pula sessões que já existem no Supabase")
    args = parser.parse_args()

    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")):
        print("[!] Variáveis SUPABASE_URL e SUPABASE_KEY não setadas no shell.")
        print("    Exemplo (Windows CMD):")
        print('      set SUPABASE_URL=https://xxxxx.supabase.co')
        print('      set SUPABASE_KEY=eyJ...')
        return 1

    sessions_dir = Path(args.sessions_dir).resolve()
    if not sessions_dir.exists():
        print(f"[!] Pasta não encontrada: {sessions_dir}")
        return 1

    # Garante que conseguimos importar o app
    backend_dir = Path(__file__).resolve().parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from app.db import supabase_client, supabase_repo  # type: ignore

    if not supabase_client.is_enabled():
        print("[!] Supabase não está habilitado mesmo com env vars — checa SUPABASE_URL/KEY")
        return 1

    client = supabase_client.get_client()
    if client is None:
        print("[!] Falha ao conectar no Supabase")
        return 1

    # Lista session_ids já existentes no Supabase pra pular se --skip-existing
    existing: set[str] = set()
    if args.skip_existing:
        try:
            res = client.table("sessions").select("session_id").execute()
            existing = {row["session_id"] for row in (res.data or [])}
            print(f"[i] {len(existing)} sessões já existem no Supabase — vão ser puladas")
        except Exception as e:
            print(f"[!] Falha ao listar existentes: {e}")

    session_dirs = [p for p in sessions_dir.iterdir()
                    if p.is_dir() and (p / "session.db").exists()]
    print(f"[i] Encontradas {len(session_dirs)} sessões em {sessions_dir}\n")

    success = 0
    failed = 0
    skipped = 0

    for sd in session_dirs:
        session_id = sd.name
        if session_id in existing:
            print(f"[skip] {session_id} (já existe)")
            skipped += 1
            continue

        try:
            metadata, laps = _read_session_db(sd / "session.db", session_id)
            parquet_bytes = (sd / "telemetry.parquet").read_bytes()

            print(f"[..] {session_id}: {metadata['track_location']} | "
                  f"{metadata['num_laps']} laps | {len(parquet_bytes) / 1024:.0f}KB parquet")

            t0 = time.time()
            ok_db = supabase_repo.upsert_session(metadata, laps)
            ok_storage = supabase_repo.upload_telemetry_bytes(session_id, parquet_bytes)
            elapsed = time.time() - t0

            if ok_db and ok_storage:
                print(f"[OK] {session_id} migrada em {elapsed:.1f}s")
                success += 1
            else:
                print(f"[ERR] {session_id} parcial (db={ok_db}, storage={ok_storage})")
                failed += 1
        except Exception as e:
            print(f"[ERR] {session_id}: {e.__class__.__name__}: {e}")
            failed += 1

    print()
    print("─" * 60)
    print(f"  Sucesso: {success}")
    print(f"  Falha:   {failed}")
    print(f"  Pulado:  {skipped}")
    print("─" * 60)
    return 0 if failed == 0 else 2


def _read_session_db(db_path: Path, session_id: str) -> tuple[dict, list[dict]]:
    conn = sqlite3.connect(db_path)
    info = dict(conn.execute("SELECT key, value FROM session_info").fetchall())
    lap_rows = conn.execute(
        "SELECT lap_number, lap_time_s, sector1_s, sector2_s, sector3_s, invalidated FROM laps"
    ).fetchall()
    conn.close()

    metadata = {
        "session_id": info.get("session_id", session_id),
        "started_at": info.get("started_at", ""),
        "track_location": info.get("track_location", "unknown") or "unknown",
        "track_variation": info.get("track_variation", "") or "",
        "track_length_m": float(info.get("track_length_m", 0.0) or 0.0),
        "num_samples": int(info.get("num_samples", 0) or 0),
        "num_laps": int(info.get("num_laps", 0) or 0),
        "car_name": info.get("car_name", "") or "",
        "car_class_name": info.get("car_class_name", "") or "",
        "car_class_id": int(info.get("car_class_id", 0) or 0),
        "telemetry_path": f"{session_id}/telemetry.parquet",
    }
    laps = [
        {
            "session_id": session_id,
            "lap_number": int(n),
            "lap_time_s": float(t) if t is not None else None,
            "sector1_s": float(s1) if s1 is not None else None,
            "sector2_s": float(s2) if s2 is not None else None,
            "sector3_s": float(s3) if s3 is not None else None,
            "invalidated": int(inv or 0),
        }
        for (n, t, s1, s2, s3, inv) in lap_rows
    ]
    return metadata, laps


if __name__ == "__main__":
    raise SystemExit(main())
