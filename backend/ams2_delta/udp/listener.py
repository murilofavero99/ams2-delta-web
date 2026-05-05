"""
Listener UDP: escuta a porta 5606, decodifica pacotes, correlaciona telemetria
com timings (pra saber em qual volta/setor cada sample foi tirado) e grava
a sessão em disco.

Estrutura de uma sessão gravada:
    sessions/<session_id>/
        session.db        -- SQLite com metadados (voltas, setores, pista, data)
        telemetry.parquet -- Parquet columnar com todos os samples de telemetria

Como executar:
    python -m ams2_delta.udp.listener --name "montreal_pratica"

Pressione Ctrl+C para finalizar e gravar.
"""
from __future__ import annotations

import argparse
import os
import socket
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

DEFAULT_UPLOAD_URL = "https://ams2-delta-web-production.up.railway.app"

from ams2_delta.udp.packets import (
    MAX_PACKET_SIZE, UDP_PORT,
    TelemetryPacket, TimingsPacket, RaceDataPacket, GameStatePacket,
    ParticipantVehicleNamesPacket, VehicleClassNamesPacket,
    parse_packet,
)


# ----------------------------------------------------------------------------
# Estado corrente da sessão em memória
# ----------------------------------------------------------------------------

@dataclass
class LapInfo:
    """Informações consolidadas de uma volta completada."""
    lap_number: int
    lap_time_s: float
    sector1_time_s: Optional[float] = None
    sector2_time_s: Optional[float] = None
    sector3_time_s: Optional[float] = None
    invalidated: bool = False


@dataclass
class SessionState:
    session_id: str
    started_at: str
    track_location: str = "unknown"
    track_variation: str = ""
    track_length_m: float = 0.0

    # Carro do jogador (auto-detect via UDP, com possibilidade de override CLI)
    car_name: str = ""
    car_class_id: int = 0
    car_class_name: str = ""
    car_name_override: bool = False  # se True, ignora auto-detect (veio da flag --car)

    # Buffer de samples de telemetria (cada sample = dict pronto p/ DataFrame)
    telemetry_buffer: list[dict] = field(default_factory=list)

    # Últimas leituras dos pacotes não-telemetria (pra enriquecer samples)
    last_timings: Optional[TimingsPacket] = None

    # Tabelas de lookup recebidas via PARTICIPANT_VEHICLE_NAMES (tipo 8)
    vehicles_by_index: dict[int, "tuple[str, int]"] = field(default_factory=dict)  # car_index -> (name, class_id)
    class_names_by_id: dict[int, str] = field(default_factory=dict)                # class_id -> class_name

    # Laps fechados
    completed_laps: list[LapInfo] = field(default_factory=list)

    # Detecção de volta nova: guardamos a última volta/setor vistos pra detectar transições
    _last_seen_lap: int = -1
    _last_seen_sector: int = -1
    _last_lap_time_shown: float = 0.0  # em seg., guardado no instante antes da transição
    _last_seen_distance: float = -1.0  # pra detectar cruzamento de linha por distância
    _instant_reset_count: int = 0      # quantos instant resets houve nesta volta


# ----------------------------------------------------------------------------
# Construção do sample de telemetria (uma linha do Parquet)
# ----------------------------------------------------------------------------

def build_telemetry_sample(tel: TelemetryPacket,
                           timings: Optional[TimingsPacket],
                           wall_time: float) -> dict:
    """
    Converte um pacote de telemetria + último timings conhecido em um dict
    com TODOS os campos que vão pra uma linha do Parquet.
    """
    local = timings.local_participant() if timings else None

    return {
        # Tempo
        "wall_time": wall_time,
        "packet_number": tel.header.packet_number,

        # Contexto de volta (vem do pacote TIMINGS, não da telemetria)
        "current_lap": local.current_lap if local else -1,
        "current_lap_distance": local.current_lap_distance if local else -1,
        "current_time_s": local.current_time if local else 0.0,
        "current_sector_time_s": local.current_sector_time if local else 0.0,
        "sector_index": local.sector_index if local else -1,
        "lap_invalidated": local.is_lap_invalidated if local else False,

        # Inputs filtrados (os corretos pro Delta)
        "throttle_pct": tel.throttle_pct,
        "brake_pct": tel.brake_pct,
        "steering_pct": tel.steering_pct,
        "clutch_pct": (tel.clutch / 255.0) * 100.0,

        # Inputs não-filtrados (bônus)
        "throttle_raw": tel.throttle,
        "brake_raw": tel.brake,

        # Velocidade e motor
        "speed_kmh": tel.speed_kmh,
        "speed_ms": tel.speed_ms,
        "rpm": tel.rpm,
        "max_rpm": tel.max_rpm,
        "gear": tel.gear,
        "num_gears": tel.num_gears,

        # Posição mundial (offset 542 — o que o Gemini errava)
        "world_x": tel.world_x,
        "world_y": tel.world_y,
        "world_z": tel.world_z,

        # G-forces (local acceleration) — úteis pra comparar curvas
        "accel_local_x": tel.local_acceleration[0],
        "accel_local_y": tel.local_acceleration[1],
        "accel_local_z": tel.local_acceleration[2],

        # Combustível
        "fuel_level_pct": tel.fuel_level_pct,   # 0-100% do tanque
        "fuel_capacity": tel.fuel_capacity,

        # Damage
        "aero_damage": tel.aero_damage,
        "engine_damage": tel.engine_damage,

        # Setup
        "brake_bias_pct": tel.brake_bias_pct,    # aproximação 0-100%
        "brake_bias_raw": tel.brake_bias,        # valor bruto 0-255 da spec
    }


# ----------------------------------------------------------------------------
# Detecção de voltas completadas
# ----------------------------------------------------------------------------

def detect_lap_completion(state: SessionState, timings: TimingsPacket) -> None:
    """
    Detecta quando uma volta foi fechada e registra o tempo.

    Suporta dois modos de detecção:
    1. current_lap incrementou (modo normal — corrida/qualificação)
    2. current_lap_distance voltou pra ~0 sem incrementar current_lap
       (instant reset do Time Trial — o piloto resetou e completou uma volta nova)
    """
    local = timings.local_participant()
    if local is None:
        return

    lap = local.current_lap
    sector = local.sector_index
    distance = local.current_lap_distance

    # Primeira vez — apenas inicializa
    if state._last_seen_lap == -1:
        state._last_seen_lap = lap
        state._last_seen_sector = sector
        state._last_seen_distance = distance
        return

    def _register_lap(lap_number: int, invalidated: bool) -> None:
        lap_time = _extract_last_lap_time(state, lap_number)
        if lap_time > 0:
            state.completed_laps.append(LapInfo(
                lap_number=lap_number,
                lap_time_s=lap_time,
                invalidated=invalidated,
            ))
            print(f"  → Volta {lap_number} completada em {format_time(lap_time)}"
                  + (" [INVALIDADA]" if invalidated else ""))

    # -----------------------------------------------------------------------
    # Modo 1: current_lap incrementou (modo normal)
    # -----------------------------------------------------------------------
    if lap > state._last_seen_lap:
        _register_lap(state._last_seen_lap, local.is_lap_invalidated)

    # -----------------------------------------------------------------------
    # Modo 2: instant reset (Time Trial)
    # Detectado quando current_lap_distance caiu bruscamente (> 200m de queda)
    # sem que current_lap tenha incrementado. Indica que o piloto usou o
    # instant reset. Se a distância anterior era > 80% da pista, a volta
    # foi provavelmente completada antes do reset.
    # -----------------------------------------------------------------------
    elif (state._last_seen_distance > 0 and
          distance < 100 and
          state._last_seen_distance > (state.track_length_m * 0.8 if state.track_length_m > 0 else 3000)):
        # O piloto estava perto do fim da pista e agora está em 0 = cruzou a linha
        _register_lap(lap, local.is_lap_invalidated)
        state._instant_reset_count += 1
        print(f"  [i] Instant reset detectado #{state._instant_reset_count} — "
              f"distância anterior: {state._last_seen_distance:.0f}m")

    state._last_seen_lap = lap
    state._last_seen_sector = sector
    state._last_seen_distance = distance


def _extract_last_lap_time(state: SessionState, lap_number: int) -> float:
    """Pega o maior current_time_s visto para a volta especificada no buffer."""
    max_t = 0.0
    # Varrer de trás pra frente é mais rápido (samples recentes)
    for sample in reversed(state.telemetry_buffer):
        if sample["current_lap"] == lap_number:
            if sample["current_time_s"] > max_t:
                max_t = sample["current_time_s"]
        elif sample["current_lap"] < lap_number:
            break
    return max_t


def format_time(seconds: float) -> str:
    """Formata segundos como M:SS.mmm."""
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:06.3f}"


# ----------------------------------------------------------------------------
# Persistência em disco (Parquet + SQLite)
# ----------------------------------------------------------------------------

def save_session(state: SessionState, sessions_dir: Path) -> Path:
    """Grava a sessão completa em disco. Retorna o path da pasta da sessão."""
    session_dir = sessions_dir / state.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Parquet — telemetria
    if state.telemetry_buffer:
        df = pd.DataFrame(state.telemetry_buffer)
        parquet_path = session_dir / "telemetry.parquet"
        df.to_parquet(parquet_path, index=False, compression="snappy")
        print(f"[+] {len(df)} samples gravados em {parquet_path}")
    else:
        print("[!] Nenhum sample de telemetria capturado.")

    # SQLite — metadados
    db_path = session_dir / "session.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS session_info (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS laps (
            lap_number INTEGER PRIMARY KEY,
            lap_time_s REAL,
            sector1_s REAL,
            sector2_s REAL,
            sector3_s REAL,
            invalidated INTEGER
        );
    """)

    cur.executemany(
        "INSERT OR REPLACE INTO session_info(key, value) VALUES (?, ?)",
        [
            ("session_id", state.session_id),
            ("started_at", state.started_at),
            ("track_location", state.track_location),
            ("track_variation", state.track_variation),
            ("track_length_m", str(state.track_length_m)),
            ("num_samples", str(len(state.telemetry_buffer))),
            ("num_laps", str(len(state.completed_laps))),
            ("car_name", state.car_name),
            ("car_class_name", state.car_class_name),
            ("car_class_id", str(state.car_class_id)),
        ]
    )

    cur.executemany(
        "INSERT OR REPLACE INTO laps VALUES (?, ?, ?, ?, ?, ?)",
        [
            (lap.lap_number, lap.lap_time_s,
             lap.sector1_time_s, lap.sector2_time_s, lap.sector3_time_s,
             int(lap.invalidated))
            for lap in state.completed_laps
        ]
    )

    conn.commit()
    conn.close()
    print(f"[+] Metadados gravados em {db_path}")

    return session_dir


def resolve_player_car(state: SessionState) -> None:
    """
    Tenta cruzar dados do TimingsPacket (local_participant_index -> car_index)
    com a tabela vehicles_by_index para determinar nome/classe do carro do jogador.

    Não faz nada se o usuário já passou --car (override) ou se ainda não há dados
    suficientes. Idempotente — pode ser chamado várias vezes.
    """
    if state.car_name_override:
        return
    if not state.last_timings or not state.vehicles_by_index:
        return

    local = state.last_timings.local_participant()
    if local is None:
        return

    info = state.vehicles_by_index.get(local.car_index)
    if info is None:
        return

    name, class_id = info
    if name and name != state.car_name:
        state.car_name = name
        state.car_class_id = class_id
        state.car_class_name = state.class_names_by_id.get(class_id, "")
        cls_str = f" ({state.car_class_name})" if state.car_class_name else ""
        print(f"[i] Carro detectado: {state.car_name}{cls_str}")
    elif class_id and not state.car_class_name:
        # Nome já estava certo, mas classe pode ter chegado depois
        cls_name = state.class_names_by_id.get(class_id, "")
        if cls_name:
            state.car_class_name = cls_name
            print(f"[i] Classe detectada: {cls_name}")


def upload_session_to_supabase(session_dir: Path, session_id: str) -> bool:
    """
    Tenta upload direto para o Supabase (Postgres + Storage), pulando o Railway.

    Requer SUPABASE_URL e SUPABASE_KEY no ambiente. Retorna False (silenciosamente,
    sem mensagens de erro) se as credenciais não estão configuradas, pra deixar o
    chamador cair no fallback HTTP.
    """
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")):
        return False

    db_path = session_dir / "session.db"
    parquet_path = session_dir / "telemetry.parquet"
    if not db_path.exists() or not parquet_path.exists():
        print(f"[!] Upload Supabase abortado: arquivos não encontrados em {session_dir}")
        return False

    try:
        import sqlite3 as _sqlite

        # Importa o módulo do backend (mesmo projeto Python)
        backend_dir = Path(__file__).resolve().parents[2]
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from app.db import supabase_repo  # type: ignore

        # Lê metadata + laps do session.db
        conn = _sqlite.connect(db_path)
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

        print(f"[*] Subindo direto para o Supabase...")
        t0 = time.time()
        ok_db = supabase_repo.upsert_session(metadata, laps)
        ok_storage = supabase_repo.upload_telemetry_bytes(session_id, parquet_path.read_bytes())
        elapsed = time.time() - t0

        if ok_db and ok_storage:
            print(f"[+] Upload Supabase concluído em {elapsed:.1f}s — disponível no app!")
            return True

        print(f"[!] Upload Supabase parcial após {elapsed:.1f}s "
              f"(postgres={ok_db}, storage={ok_storage}) — caindo pro fallback HTTP")
        return False
    except Exception as e:
        print(f"[!] Upload Supabase falhou ({e.__class__.__name__}: {e}) — caindo pro fallback HTTP")
        return False


def upload_session_to_cloud(session_dir: Path, session_id: str, upload_url: str,
                            timeout: int = 120) -> bool:
    """
    Faz upload da sessão (session.db + telemetry.parquet) para o backend cloud.
    Retorna True em sucesso, False em falha. Nunca lança exceção.
    """
    db_path = session_dir / "session.db"
    parquet_path = session_dir / "telemetry.parquet"

    if not db_path.exists() or not parquet_path.exists():
        print(f"[!] Upload abortado: arquivos da sessão não encontrados em {session_dir}")
        return False

    endpoint = f"{upload_url.rstrip('/')}/sessions/upload"
    print(f"[*] Enviando sessão para {endpoint} ...")
    print(f"      session.db        : {db_path.stat().st_size / 1024:.1f} KB")
    print(f"      telemetry.parquet : {parquet_path.stat().st_size / 1024:.1f} KB")

    t0 = time.time()
    try:
        with open(db_path, "rb") as fdb, open(parquet_path, "rb") as fpq:
            files = {
                "session_db": ("session.db", fdb, "application/octet-stream"),
                "telemetry": ("telemetry.parquet", fpq, "application/octet-stream"),
            }
            resp = requests.post(
                endpoint,
                params={"session_id": session_id},
                files=files,
                timeout=timeout,
            )
        elapsed = time.time() - t0

        if resp.status_code == 200:
            print(f"[+] Upload concluído em {elapsed:.1f}s — sessão disponível no app cloud!")
            return True

        print(f"[!] Upload FALHOU (HTTP {resp.status_code}) após {elapsed:.1f}s")
        try:
            print(f"      Resposta: {resp.json()}")
        except Exception:
            print(f"      Resposta: {resp.text[:500]}")
        print(f"[!] A sessão continua salva localmente em {session_dir}")
        print(f"[!] Você pode tentar reenviar depois com: upload_sessions.bat")
        return False

    except requests.exceptions.Timeout:
        print(f"[!] Upload FALHOU: timeout após {timeout}s. Verifique sua conexão.")
        print(f"[!] A sessão continua salva localmente em {session_dir}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"[!] Upload FALHOU: erro de conexão ({e.__class__.__name__})")
        print(f"      O Railway está online? URL: {upload_url}")
        print(f"[!] A sessão continua salva localmente em {session_dir}")
        return False
    except Exception as e:
        print(f"[!] Upload FALHOU: {e.__class__.__name__}: {e}")
        print(f"[!] A sessão continua salva localmente em {session_dir}")
        return False


# ----------------------------------------------------------------------------
# Loop principal
# ----------------------------------------------------------------------------

def run(session_name: str, sessions_dir: Path, port: int = UDP_PORT,
        bind_ip: str = "0.0.0.0", upload_url: Optional[str] = None,
        car_override: Optional[str] = None) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{timestamp}_{session_name}"
    state = SessionState(session_id=session_id, started_at=timestamp)
    if car_override:
        state.car_name = car_override
        state.car_name_override = True

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Buffer de recepção GRANDE (8 MB) para não perder pacotes quando o jogo envia
    # em burst. Default do SO é só ~200KB, insuficiente com Frequency 9/10 que manda
    # múltiplos pacotes a cada tick. Isso era a causa do sample rate baixo.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        actual_buf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        print(f"[i] Buffer de recepção UDP: {actual_buf / 1024:.0f} KB")
    except OSError as e:
        print(f"[!] Não consegui aumentar buffer UDP: {e}")

    sock.bind((bind_ip, port))
    sock.settimeout(1.0)

    print(f"[*] Ouvindo AMS2 em {bind_ip}:{port}")
    print(f"[*] Sessão: {session_id}")
    if car_override:
        print(f"[*] Carro (manual): {car_override}")
    else:
        print(f"[*] Carro: aguardando auto-detect via UDP...")
    if upload_url:
        print(f"[*] Upload automático ativado: {upload_url}")
    else:
        print(f"[*] Upload automático: desativado")
    print(f"[*] Ctrl+C para finalizar e salvar\n")

    last_log_count = 0
    log_every = 300  # printa status a cada N samples

    # Contadores por tipo de pacote para diagnóstico
    packet_counts = {"telemetry": 0, "timings": 0, "race_data": 0,
                     "game_state": 0, "vehicle_names": 0, "class_names": 0,
                     "unknown": 0, "parse_error": 0}
    start_time = time.time()

    try:
        while True:
            try:
                data, _addr = sock.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                continue

            pkt = parse_packet(data)
            if pkt is None:
                packet_counts["unknown"] += 1
                continue

            wall_time = time.time()

            if isinstance(pkt, TelemetryPacket):
                packet_counts["telemetry"] += 1
                sample = build_telemetry_sample(pkt, state.last_timings, wall_time)
                state.telemetry_buffer.append(sample)

                if len(state.telemetry_buffer) - last_log_count >= log_every:
                    last_log_count = len(state.telemetry_buffer)
                    elapsed = wall_time - start_time
                    rate = last_log_count / elapsed if elapsed > 0 else 0
                    print(f"  Samples: {last_log_count:>5} ({rate:4.1f} Hz) | "
                          f"{pkt.speed_kmh:5.1f} km/h | "
                          f"Gear {pkt.gear:>2} | "
                          f"RPM {pkt.rpm:>5} | "
                          f"Thr {pkt.throttle_pct:5.1f}% | "
                          f"Brk {pkt.brake_pct:5.1f}%")

            elif isinstance(pkt, TimingsPacket):
                packet_counts["timings"] += 1
                state.last_timings = pkt
                detect_lap_completion(state, pkt)
                resolve_player_car(state)

            elif isinstance(pkt, ParticipantVehicleNamesPacket):
                packet_counts["vehicle_names"] += 1
                for v in pkt.vehicles:
                    state.vehicles_by_index[v.index] = (v.name, v.class_id)
                resolve_player_car(state)

            elif isinstance(pkt, VehicleClassNamesPacket):
                packet_counts["class_names"] += 1
                for c in pkt.classes:
                    state.class_names_by_id[c.class_id] = c.name
                resolve_player_car(state)

            elif isinstance(pkt, RaceDataPacket):
                packet_counts["race_data"] += 1
                if pkt.track_location and state.track_location == "unknown":
                    state.track_location = pkt.track_location
                    state.track_variation = pkt.track_variation
                    state.track_length_m = pkt.track_length
                    print(f"[i] Pista: {pkt.track_location} / "
                          f"{pkt.track_variation} ({pkt.track_length:.0f}m)")
                # Atualiza mesmo depois (casos onde só o length veio preenchido em pacote posterior)
                if pkt.track_length > 0 and state.track_length_m == 0:
                    state.track_length_m = pkt.track_length

            elif isinstance(pkt, GameStatePacket):
                packet_counts["game_state"] += 1

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n[*] Captura finalizada após {elapsed:.1f}s")
        print(f"[*] Pacotes recebidos:")
        for ptype, count in packet_counts.items():
            rate = count / elapsed if elapsed > 0 else 0
            print(f"      {ptype:15s}: {count:>6} ({rate:5.1f} Hz)")
        if state.car_name:
            origin = "manual" if state.car_name_override else "auto"
            cls_str = f" ({state.car_class_name})" if state.car_class_name else ""
            print(f"[*] Carro: {state.car_name}{cls_str} [{origin}]")
        else:
            print(f"[!] Carro NÃO identificado — passe --car \"Nome do carro\" pra próxima")
        print(f"[*] Gravando sessão...")
        session_dir = save_session(state, sessions_dir)

        # Estratégia de upload:
        # 1. Tenta Supabase direto (se SUPABASE_URL/KEY estão setadas)
        # 2. Se não conseguir, faz HTTP POST pro Railway (fallback)
        if upload_url:
            print()
            ok_supabase = upload_session_to_supabase(session_dir, state.session_id)
            if not ok_supabase:
                upload_session_to_cloud(session_dir, state.session_id, upload_url)
        else:
            print(f"[i] Para subir esta sessão para o cloud depois, rode: upload_sessions.bat")


def main() -> None:
    parser = argparse.ArgumentParser(description="Listener UDP para AMS2/PCARS2")
    parser.add_argument("--name", required=True, help="Nome descritivo da sessão (ex.: montreal_pratica)")
    parser.add_argument("--port", type=int, default=UDP_PORT, help=f"Porta UDP (default {UDP_PORT})")
    parser.add_argument("--sessions-dir", default="sessions",
                        help="Pasta onde as sessões serão gravadas")
    parser.add_argument("--upload-url", default=None,
                        help=f"URL do backend cloud para upload automático (default: env AMS2_UPLOAD_URL ou {DEFAULT_UPLOAD_URL})")
    parser.add_argument("--no-upload", action="store_true",
                        help="Desativa upload automático após Ctrl+C")
    parser.add_argument("--car", default=None,
                        help="Nome do carro (override manual). Se omitido, auto-detect via UDP.")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir).resolve()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    if args.no_upload:
        upload_url = None
    else:
        upload_url = args.upload_url or os.environ.get("AMS2_UPLOAD_URL") or DEFAULT_UPLOAD_URL

    run(args.name, sessions_dir, args.port, upload_url=upload_url, car_override=args.car)


if __name__ == "__main__":
    main()
