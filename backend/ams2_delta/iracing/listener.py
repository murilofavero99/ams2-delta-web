"""
Captura de telemetria do iRacing via Memory-Mapped Files.

Diferente do AMS2 (que usa UDP), o iRacing expoe os dados por shared
memory atraves do irsdk. Esta implementacao:

  1. Conecta no irsdk e poola a 60 Hz
  2. Le campos de telemetria + SessionInfo (YAML) pra pista/carro
  3. Constroi samples no MESMO schema usado pelo AMS2 (coluna por coluna),
     pra que toda a pipeline de analise/IA/Supabase funcione sem mudanca
  4. Detecta voltas pelo incremento de Lap
  5. Reaproveita save_session + upload do listener AMS2

Observacoes de mapeamento iRacing -> schema AMS2:
  - world_x/world_z: iRacing nao expoe coords globais; integramos a partir
    de VelocityX/Y + YawNorth pra ter um traçado de pista relativo (com
    origem arbitraria mas consistente dentro de uma volta).
  - sector_index/sector1_s/2/3: iRacing nao expoe setores em runtime; fica
    -1 e None respectivamente. lap_time_s vem de LapLastLapTime.
  - lap_invalidated: iRacing nao tem flag direto; deixamos False.
  - aero_damage/engine_damage: zerados (nao expostos pelo irsdk padrao).

Como rodar:
    pip install pyirsdk
    python -m ams2_delta.iracing.listener --name "spa_pratica"

Ctrl+C para finalizar.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Importa irsdk lazy — so falha quando o usuario realmente roda o listener,
# nao quando o pacote eh importado pelo resto do app.
try:
    import irsdk  # type: ignore
except ImportError:
    irsdk = None

# Reusa toda a infra de gravacao/upload do AMS2
from ams2_delta.udp.listener import (
    DEFAULT_UPLOAD_URL, LapInfo, SessionState,
    format_time, save_session,
    upload_session_to_cloud, upload_session_to_supabase,
)


POLL_HZ = 60
TICK_S = 1.0 / POLL_HZ


# ---------------------------------------------------------------------------
# Helpers de SessionInfo (YAML do iRacing)
# ---------------------------------------------------------------------------

def _parse_track_length(raw: str) -> float:
    """'5.793 km' -> 5793.0; '3.50 mi' -> 5632.7. Aceita varios formatos."""
    if not raw:
        return 0.0
    m = re.search(r"([\d.]+)\s*(km|mi|m)", raw.lower())
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == "km":
        return val * 1000.0
    if unit == "mi":
        return val * 1609.34
    return val  # m


def _extract_track_and_car(ir, state: SessionState) -> None:
    """
    Le SessionInfo (YAML) e popula state com pista + carro do jogador.
    Idempotente — pode ser chamado varias vezes.
    """
    info = ir["SessionInfo"]
    weekend = ir["WeekendInfo"]
    drivers = ir["DriverInfo"]

    if weekend and state.track_location == "unknown":
        track_name = (
            weekend.get("TrackDisplayName")
            or weekend.get("TrackName")
            or "unknown"
        )
        config = weekend.get("TrackConfigName") or ""
        length_raw = weekend.get("TrackLength") or weekend.get("TrackLengthOfficial") or ""
        state.track_location = str(track_name)
        state.track_variation = str(config)
        state.track_length_m = _parse_track_length(str(length_raw))
        print(f"[i] Pista: {state.track_location}"
              + (f" / {state.track_variation}" if state.track_variation else "")
              + f" ({state.track_length_m:.0f}m)")

    if drivers and not state.car_name_override:
        idx = drivers.get("DriverCarIdx")
        drv_list = drivers.get("Drivers") or []
        if idx is not None and 0 <= idx < len(drv_list):
            d = drv_list[idx]
            new_name = d.get("CarScreenName") or d.get("CarPath") or ""
            new_class = d.get("CarClassShortName") or d.get("CarClassID") or ""
            if new_name and new_name != state.car_name:
                state.car_name = str(new_name)
                state.car_class_name = str(new_class)
                cls = f" ({state.car_class_name})" if state.car_class_name else ""
                print(f"[i] Carro detectado: {state.car_name}{cls}")


# ---------------------------------------------------------------------------
# Sample builder
# ---------------------------------------------------------------------------

def _safe_get(ir, key: str, default=0.0):
    v = ir[key]
    return v if v is not None else default


def build_sample(ir, wall_time: float, world_x: float, world_z: float,
                 steer_max_rad: float) -> dict:
    """
    Le os campos do irsdk e monta um dict no schema do AMS2.
    """
    speed_ms = float(_safe_get(ir, "Speed", 0.0))
    rpm = float(_safe_get(ir, "RPM", 0.0))
    gear = int(_safe_get(ir, "Gear", 0))
    throttle = float(_safe_get(ir, "Throttle", 0.0))
    brake = float(_safe_get(ir, "Brake", 0.0))
    clutch = float(_safe_get(ir, "Clutch", 1.0))   # iRacing: 1 = solto, 0 = pressionado
    steer = float(_safe_get(ir, "SteeringWheelAngle", 0.0))

    lap = int(_safe_get(ir, "Lap", -1))
    lap_dist = float(_safe_get(ir, "LapDist", -1.0))
    cur_time = float(_safe_get(ir, "LapCurrentLapTime", 0.0))

    lat_accel = float(_safe_get(ir, "LatAccel", 0.0))
    lon_accel = float(_safe_get(ir, "LongAccel", 0.0))
    vert_accel = float(_safe_get(ir, "VertAccel", 0.0))

    fuel_pct = float(_safe_get(ir, "FuelLevelPct", 0.0)) * 100.0
    fuel_capacity = float(_safe_get(ir, "FuelLevel", 0.0)) / max(fuel_pct / 100.0, 1e-6) if fuel_pct > 0 else 0.0
    brake_bias_raw = float(_safe_get(ir, "dcBrakeBias", 0.0))

    # steering em % (-100..100), assumindo maximo do volante do carro
    if steer_max_rad > 0:
        steer_pct = (steer / steer_max_rad) * 100.0
    else:
        steer_pct = math.degrees(steer)  # fallback: graus ~ %
    steer_pct = max(-100.0, min(100.0, steer_pct))

    return {
        "wall_time": wall_time,
        "packet_number": 0,  # nao aplicavel no iRacing (sem pacotes)

        "current_lap": lap,
        "current_lap_distance": lap_dist,
        "current_time_s": cur_time,
        "current_sector_time_s": 0.0,
        "sector_index": -1,
        "lap_invalidated": False,

        "throttle_pct": throttle * 100.0,
        "brake_pct": brake * 100.0,
        "steering_pct": steer_pct,
        "clutch_pct": (1.0 - clutch) * 100.0,  # inverte: 100% = pedal afundado

        "throttle_raw": int(throttle * 255),
        "brake_raw": int(brake * 255),

        "speed_kmh": speed_ms * 3.6,
        "speed_ms": speed_ms,
        "rpm": rpm,
        "max_rpm": 0.0,
        "gear": gear,
        "num_gears": 0,

        "world_x": world_x,
        "world_y": 0.0,
        "world_z": world_z,

        "accel_local_x": lat_accel,
        "accel_local_y": vert_accel,
        "accel_local_z": lon_accel,

        "fuel_level_pct": fuel_pct,
        "fuel_capacity": fuel_capacity,

        "aero_damage": 0.0,
        "engine_damage": 0.0,

        "brake_bias_pct": brake_bias_raw,
        "brake_bias_raw": int(brake_bias_raw),
    }


# ---------------------------------------------------------------------------
# Detector de voltas (compativel com a pipeline AMS2)
# ---------------------------------------------------------------------------

def detect_lap_completion(state: SessionState, ir, lap_now: int) -> None:
    """Quando Lap incrementa, registra a volta anterior usando LapLastLapTime."""
    if state._last_seen_lap == -1:
        state._last_seen_lap = lap_now
        return
    if lap_now > state._last_seen_lap:
        last_time = float(_safe_get(ir, "LapLastLapTime", 0.0))
        if last_time > 0:
            state.completed_laps.append(LapInfo(
                lap_number=state._last_seen_lap,
                lap_time_s=last_time,
                invalidated=False,
            ))
            print(f"  -> Volta {state._last_seen_lap} completada em {format_time(last_time)}")
    state._last_seen_lap = lap_now


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run(session_name: str, sessions_dir: Path,
        upload_url: Optional[str] = None,
        car_override: Optional[str] = None) -> None:
    if irsdk is None:
        print("[!] Modulo 'irsdk' nao instalado. Rode: pip install pyirsdk")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{timestamp}_{session_name}"
    state = SessionState(session_id=session_id, started_at=timestamp)
    if car_override:
        state.car_name = car_override
        state.car_name_override = True

    ir = irsdk.IRSDK()

    print(f"[*] Conectando ao iRacing...")
    print(f"[*] Sessao: {session_id}")
    if car_override:
        print(f"[*] Carro (manual): {car_override}")
    print(f"[*] Ctrl+C para finalizar e salvar\n")

    # Aguarda iRacing aparecer
    while not ir.startup():
        time.sleep(0.5)
        # Imprime so esporadicamente pra nao poluir
    print(f"[+] Conectado ao iRacing.")

    # Volante max em radianos (necessario pra normalizar steering_pct)
    steer_max_rad = float(_safe_get(ir, "SteeringWheelAngleMax", 0.0))

    # Estado pra integracao de world position
    last_t = time.time()
    world_x = 0.0
    world_z = 0.0
    last_lap_for_xz_reset = -1

    last_log_count = 0
    log_every = 300
    sample_count = 0
    start_time = time.time()

    try:
        while True:
            t0 = time.time()

            if not ir.is_connected:
                print("[!] iRacing desconectou — aguardando reconexao...")
                while not ir.startup():
                    time.sleep(0.5)
                print("[+] Reconectado.")
                last_t = time.time()
                continue

            ir.freeze_var_buffer_latest()

            # SessionInfo so muda raramente — barato chamar
            _extract_track_and_car(ir, state)
            if steer_max_rad <= 0:
                steer_max_rad = float(_safe_get(ir, "SteeringWheelAngleMax", 0.0))

            on_track = bool(_safe_get(ir, "IsOnTrack", False))
            if not on_track:
                # Pula amostras quando piloto esta no garagem/replay
                time.sleep(TICK_S)
                continue

            # Integra world position via velocity + yaw
            now = time.time()
            dt = max(1e-3, now - last_t)
            last_t = now

            vel_x = float(_safe_get(ir, "VelocityX", 0.0))  # forward (m/s)
            vel_y = float(_safe_get(ir, "VelocityY", 0.0))  # lateral (m/s)
            yaw = float(_safe_get(ir, "YawNorth", 0.0))      # rad

            # Reseta origem a cada nova volta pra que cada volta sobreponha
            # bem no traçado (sem drift acumulado entre voltas)
            cur_lap = int(_safe_get(ir, "Lap", -1))
            if cur_lap != last_lap_for_xz_reset:
                world_x = 0.0
                world_z = 0.0
                last_lap_for_xz_reset = cur_lap

            # Velocidade em coords globais
            world_x += dt * (vel_x * math.cos(yaw) - vel_y * math.sin(yaw))
            world_z += dt * (vel_x * math.sin(yaw) + vel_y * math.cos(yaw))

            sample = build_sample(ir, now, world_x, world_z, steer_max_rad)
            state.telemetry_buffer.append(sample)
            sample_count += 1

            detect_lap_completion(state, ir, cur_lap)

            if sample_count - last_log_count >= log_every:
                last_log_count = sample_count
                elapsed = now - start_time
                rate = sample_count / elapsed if elapsed > 0 else 0
                print(f"  Samples: {sample_count:>5} ({rate:4.1f} Hz) | "
                      f"{sample['speed_kmh']:5.1f} km/h | "
                      f"Gear {sample['gear']:>2} | "
                      f"RPM {sample['rpm']:>5.0f} | "
                      f"Thr {sample['throttle_pct']:5.1f}% | "
                      f"Brk {sample['brake_pct']:5.1f}%")

            # Pacing
            sleep_for = TICK_S - (time.time() - t0)
            if sleep_for > 0:
                time.sleep(sleep_for)

    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\n\n[*] Captura finalizada apos {elapsed:.1f}s")
        print(f"[*] Total samples: {sample_count} ({sample_count / elapsed if elapsed > 0 else 0:.1f} Hz)")
        if state.car_name:
            origin = "manual" if state.car_name_override else "auto"
            cls_str = f" ({state.car_class_name})" if state.car_class_name else ""
            print(f"[*] Carro: {state.car_name}{cls_str} [{origin}]")
        else:
            print(f"[!] Carro NAO identificado — passe --car \"Nome\" pra proxima")
        print(f"[*] Gravando sessao...")
        session_dir = save_session(state, sessions_dir)

        if upload_url:
            print()
            ok = upload_session_to_supabase(session_dir, state.session_id)
            if not ok:
                upload_session_to_cloud(session_dir, state.session_id, upload_url)
        else:
            print(f"[i] Para subir esta sessao depois: upload_sessions.bat")

    finally:
        try:
            ir.shutdown()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Listener iRacing (irsdk)")
    parser.add_argument("--name", required=True, help="Nome descritivo da sessao")
    parser.add_argument("--sessions-dir", default="sessions",
                        help="Pasta onde as sessoes serao gravadas")
    parser.add_argument("--upload-url", default=None,
                        help=f"URL do backend cloud (default: env AMS2_UPLOAD_URL ou {DEFAULT_UPLOAD_URL})")
    parser.add_argument("--no-upload", action="store_true",
                        help="Desativa upload automatico apos Ctrl+C")
    parser.add_argument("--car", default=None,
                        help="Nome do carro (override). Se omitido, auto-detect via SessionInfo.")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions_dir).resolve()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    if args.no_upload:
        upload_url = None
    else:
        upload_url = args.upload_url or os.environ.get("AMS2_UPLOAD_URL") or DEFAULT_UPLOAD_URL

    run(args.name, sessions_dir, upload_url=upload_url, car_override=args.car)


if __name__ == "__main__":
    main()
