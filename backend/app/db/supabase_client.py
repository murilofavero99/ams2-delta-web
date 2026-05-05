"""
Cliente Supabase centralizado.

Detecta automaticamente se Supabase está configurado via env vars:
    SUPABASE_URL          -- URL do projeto (https://<id>.supabase.co)
    SUPABASE_KEY          -- service_role key (preferida no backend) ou anon key
    SUPABASE_BUCKET       -- nome do bucket de Storage (default: "telemetry")

Se não configurado, `get_client()` retorna None e o resto da app cai no
modo legacy (leitura/gravação em disco).
"""
from __future__ import annotations

import os
from typing import Optional

try:
    from supabase import Client, create_client
except ImportError:
    Client = None  # type: ignore
    create_client = None  # type: ignore


_client: Optional["Client"] = None
_initialized = False


def get_bucket_name() -> str:
    return os.environ.get("SUPABASE_BUCKET", "telemetry")


def is_enabled() -> bool:
    """True se as env vars do Supabase estão setadas."""
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_KEY"))


def get_client() -> Optional["Client"]:
    """Retorna o cliente Supabase singleton, ou None se não configurado."""
    global _client, _initialized
    if _initialized:
        return _client

    _initialized = True

    if not is_enabled():
        print("[i] Supabase não configurado (modo legacy: arquivos em disco)")
        return None

    if create_client is None:
        print("[!] Pacote 'supabase' não instalado — rode: pip install supabase")
        return None

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    try:
        _client = create_client(url, key)
        print(f"[+] Supabase conectado: {url}")
        return _client
    except Exception as e:
        print(f"[!] Falha ao conectar no Supabase: {e}")
        _client = None
        return None
