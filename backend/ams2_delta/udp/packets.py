"""
Parser UDP para Automobilista 2 / Project CARS 2.

Baseado na especificação oficial SMS_UDP_Definitions.hpp (Slightly Mad Studios).
Porta padrão: 5606. Formato: PCARS2. Endianness: little-endian. Structs packed (sem padding).

Tipos de pacote (mPacketType no header):
    0 = eCarPhysics         -> sTelemetryData   (556 bytes) - TELEMETRIA, alta frequência
    1 = eRaceDefinition     -> sRaceData        (308 bytes) - pista, track length, session info
    2 = eParticipants       -> sParticipantsData (1136 bytes) - nomes dos pilotos
    3 = eTimings            -> sTimingsData     (1059 bytes) - posições/tempos de todos
    4 = eGameState          -> sGameStateData   (24 bytes)  - estado do jogo, clima
    5 = eWeatherState       -> (não emitido pelo jogo atualmente)
    6 = eVehicleNames       -> (não emitido pelo jogo atualmente)
    7 = eTimeStats          -> sTimeStatsData   (1040 bytes) - best laps/sectors
    8 = eParticipantVehicleNames -> sParticipantVehicleNamesData - nomes de carros/classes

IMPORTANTE: o MVP só parseia integralmente os pacotes 0 e 3 (telemetria e timings),
que são os dois que mandam dados em tempo real durante uma volta. Os demais são
decodificados parcialmente apenas para contexto de sessão.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


# ----------------------------------------------------------------------------
# Constantes da spec
# ----------------------------------------------------------------------------

UDP_PORT = 5606
MAX_PACKET_SIZE = 1500

# Tamanhos oficiais de cada pacote (sPacketSize na spec)
TELEMETRY_PACKET_SIZE = 556
RACE_DATA_PACKET_SIZE = 308
PARTICIPANTS_PACKET_SIZE = 1136
TIMINGS_PACKET_SIZE = 1059
GAME_STATE_PACKET_SIZE = 24

HEADER_SIZE = 12


class PacketType(IntEnum):
    """EUDPStreamerPacketHandlerType da spec."""
    CAR_PHYSICS = 0
    RACE_DEFINITION = 1
    PARTICIPANTS = 2
    TIMINGS = 3
    GAME_STATE = 4
    WEATHER_STATE = 5
    VEHICLE_NAMES = 6
    TIME_STATS = 7
    PARTICIPANT_VEHICLE_NAMES = 8


# ----------------------------------------------------------------------------
# Header comum a todos os pacotes (PacketBase, 12 bytes)
# ----------------------------------------------------------------------------

# <  = little-endian, sem padding
# I  = uint32 (mPacketNumber)
# I  = uint32 (mCategoryPacketNumber)
# B  = uint8  (mPartialPacketIndex)
# B  = uint8  (mPartialPacketNumber)
# B  = uint8  (mPacketType)
# B  = uint8  (mPacketVersion)
_HEADER_STRUCT = struct.Struct("<IIBBBB")


@dataclass
class PacketHeader:
    packet_number: int
    category_packet_number: int
    partial_packet_index: int
    partial_packet_number: int
    packet_type: int
    packet_version: int

    @classmethod
    def unpack(cls, data: bytes) -> "PacketHeader":
        return cls(*_HEADER_STRUCT.unpack_from(data, 0))


# ----------------------------------------------------------------------------
# sTelemetryData (packet_type = 0, 556 bytes)
# Este é O pacote principal para telemetria de volta.
# ----------------------------------------------------------------------------

@dataclass
class TelemetryPacket:
    """
    Telemetria do participante sendo visualizado (geralmente o player).
    Transmitida a cada tick do UDP streamer conforme UDP Frequency configurada.
    """
    # Header
    header: PacketHeader

    # Participant info
    viewed_participant_index: int        # offset 12, signed char

    # Inputs NÃO-filtrados (0-255)
    unfiltered_throttle: int             # offset 13
    unfiltered_brake: int                # offset 14
    unfiltered_steering: int             # offset 15 (signed, -127..127)
    unfiltered_clutch: int               # offset 16

    # Car state
    car_flags: int                       # offset 17
    oil_temp_c: int                      # offset 18, signed short
    oil_pressure_kpa: int                # offset 20
    water_temp_c: int                    # offset 22, signed short
    water_pressure_kpa: int              # offset 24
    fuel_pressure_kpa: int               # offset 26
    fuel_capacity: int                   # offset 28

    # Inputs FILTRADOS pelo jogo (0-255) - estes são os que o Delta deve usar
    brake: int                           # offset 29
    throttle: int                        # offset 30
    clutch: int                          # offset 31

    fuel_level: float                    # offset 32
    speed_ms: float                      # offset 36 (metros/segundo)
    rpm: int                             # offset 40
    max_rpm: int                         # offset 42
    steering: int                        # offset 44, signed char (-127..127)
    gear_num_gears: int                  # offset 45 (low 4 bits = gear, high 4 = num_gears)
    boost_amount: int                    # offset 46
    crash_state: int                     # offset 47

    odometer_km: float                   # offset 48

    # Vetores 3D (x, y, z)
    orientation: tuple[float, float, float]        # offset 52 (3 floats)
    local_velocity: tuple[float, float, float]     # offset 64
    world_velocity: tuple[float, float, float]     # offset 76
    angular_velocity: tuple[float, float, float]   # offset 88
    local_acceleration: tuple[float, float, float] # offset 100 (G-forces do carro)
    world_acceleration: tuple[float, float, float] # offset 112

    # Damage
    aero_damage: int                     # offset 371
    engine_damage: int                   # offset 372

    # Posição MUNDIAL com precisão completa (ESTE é o offset correto!)
    world_position: tuple[float, float, float]    # offset 542 (sFullPosition[3])

    brake_bias: int                      # offset 554

    @property
    def speed_kmh(self) -> float:
        return max(0.0, self.speed_ms * 3.6)

    @property
    def gear(self) -> int:
        """Marcha atual. 0 = neutro, -1 = ré (representada como 15 no low nibble)."""
        g = self.gear_num_gears & 0x0F
        return -1 if g == 15 else g

    @property
    def num_gears(self) -> int:
        return (self.gear_num_gears >> 4) & 0x0F

    @property
    def throttle_pct(self) -> float:
        """Throttle 0-100%, usando o valor JÁ FILTRADO pelo jogo."""
        return (self.throttle / 255.0) * 100.0

    @property
    def brake_pct(self) -> float:
        """Brake 0-100%, usando o valor JÁ FILTRADO pelo jogo."""
        return (self.brake / 255.0) * 100.0

    @property
    def steering_pct(self) -> float:
        """Steering -100..+100. Negativo = esquerda, positivo = direita."""
        return (self.steering / 127.0) * 100.0

    @property
    def world_x(self) -> float:
        return self.world_position[0]

    @property
    def world_y(self) -> float:
        return self.world_position[1]

    @property
    def world_z(self) -> float:
        return self.world_position[2]

    @property
    def fuel_level_pct(self) -> float:
        """
        Nível de combustível em percentual (0-100%).
        Na spec, sFuelLevel é normalizado 0.0-1.0. Multiplica por 100 para %.
        Para obter litros absolutos, multiplique pela capacidade real do tanque
        (que varia por carro e não é transmitida de forma confiável via UDP).
        """
        return max(0.0, min(100.0, self.fuel_level * 100.0))

    @property
    def brake_bias_pct(self) -> float:
        """
        Brake bias em percentual aproximado.
        Na spec o valor é quantizado 0-255 representando o RANGE permitido pelo
        carro (geralmente algo como 50-70%). Sem conhecer o range exato de cada
        carro, uma aproximação razoável é tratar como um valor 0-100 escalado.
        Para o valor real, multiplique por 100/255 — é uma aproximação, não
        exato, mas serve para ver variações do setup.
        """
        return (self.brake_bias / 255.0) * 100.0


def parse_telemetry(data: bytes) -> Optional[TelemetryPacket]:
    """Parseia um pacote sTelemetryData. Retorna None se o tamanho estiver errado."""
    if len(data) < TELEMETRY_PACKET_SIZE:
        return None

    header = PacketHeader.unpack(data)

    # Inputs não-filtrados + car state (offsets 12..31)
    (
        viewed_participant_index,
        unfiltered_throttle, unfiltered_brake, unfiltered_steering, unfiltered_clutch,
        car_flags,
        oil_temp_c, oil_pressure_kpa,
        water_temp_c, water_pressure_kpa, fuel_pressure_kpa,
        fuel_capacity,
        brake, throttle, clutch,
    ) = struct.unpack_from("<bBBbB B hH hHH B BBB", data, 12)

    # Bloco principal: fuel_level -> crash_state (offsets 32..47)
    (fuel_level, speed_ms, rpm, max_rpm,
     steering, gear_num_gears, boost_amount, crash_state) = struct.unpack_from(
        "<ffHH bBBB", data, 32
    )

    # odometer (offset 48)
    odometer_km, = struct.unpack_from("<f", data, 48)

    # Vetores 3D a partir do offset 52
    orientation = struct.unpack_from("<fff", data, 52)
    local_velocity = struct.unpack_from("<fff", data, 64)
    world_velocity = struct.unpack_from("<fff", data, 76)
    angular_velocity = struct.unpack_from("<fff", data, 88)
    local_acceleration = struct.unpack_from("<fff", data, 100)
    world_acceleration = struct.unpack_from("<fff", data, 112)

    # Damage (offsets 371, 372)
    aero_damage, engine_damage = struct.unpack_from("<BB", data, 371)

    # Posição mundial com precisão completa (offset 542)
    world_position = struct.unpack_from("<fff", data, 542)

    # Brake bias (offset 554)
    brake_bias, = struct.unpack_from("<B", data, 554)

    return TelemetryPacket(
        header=header,
        viewed_participant_index=viewed_participant_index,
        unfiltered_throttle=unfiltered_throttle,
        unfiltered_brake=unfiltered_brake,
        unfiltered_steering=unfiltered_steering,
        unfiltered_clutch=unfiltered_clutch,
        car_flags=car_flags,
        oil_temp_c=oil_temp_c,
        oil_pressure_kpa=oil_pressure_kpa,
        water_temp_c=water_temp_c,
        water_pressure_kpa=water_pressure_kpa,
        fuel_pressure_kpa=fuel_pressure_kpa,
        fuel_capacity=fuel_capacity,
        brake=brake,
        throttle=throttle,
        clutch=clutch,
        fuel_level=fuel_level,
        speed_ms=speed_ms,
        rpm=rpm,
        max_rpm=max_rpm,
        steering=steering,
        gear_num_gears=gear_num_gears,
        boost_amount=boost_amount,
        crash_state=crash_state,
        odometer_km=odometer_km,
        orientation=orientation,
        local_velocity=local_velocity,
        world_velocity=world_velocity,
        angular_velocity=angular_velocity,
        local_acceleration=local_acceleration,
        world_acceleration=world_acceleration,
        aero_damage=aero_damage,
        engine_damage=engine_damage,
        world_position=world_position,
        brake_bias=brake_bias,
    )


# ----------------------------------------------------------------------------
# sTimingsData (packet_type = 3, 1059 bytes)
# Posição na pista, volta atual, tempo atual de volta/setor do PLAYER.
# ----------------------------------------------------------------------------

# sParticipantInfo é packed (#pragma pack(1)), 32 bytes por participante
# <hhh hhh H BB BB H BB f f H
# = 3x signed short (worldPos) + 3x signed short (orientation)
# + uint16 (currentLapDistance) + uint8 (racePosition) + uint8 (sector)
# + uint8 (highestFlag) + uint8 (pitModeSchedule)
# + uint16 (carIndex) + uint8 (raceState) + uint8 (currentLap)
# + float (currentTime) + float (currentSectorTime) + uint16 (mpParticipantIndex)
_PARTICIPANT_INFO_STRUCT = struct.Struct("<hhhhhhHBBBBHBBffH")
_PARTICIPANT_INFO_SIZE = 32  # padded conforme spec
assert _PARTICIPANT_INFO_STRUCT.size == _PARTICIPANT_INFO_SIZE, (
    f"sParticipantInfo size mismatch: {_PARTICIPANT_INFO_STRUCT.size} != {_PARTICIPANT_INFO_SIZE}"
)


@dataclass
class ParticipantInfo:
    world_x: int       # quantizado (short), em metros
    world_y: int
    world_z: int
    heading: int       # quantizado, -PI..+PI mapeado em short
    pitch: int
    bank: int
    current_lap_distance: int     # metros percorridos na volta atual
    race_position: int            # + top bit = ativo/inativo
    sector: int
    highest_flag: int
    pit_mode_schedule: int
    car_index: int
    race_state: int               # flags + invalidated lap bit
    current_lap: int
    current_time: float           # tempo da volta atual em segundos
    current_sector_time: float
    mp_participant_index: int

    @property
    def is_active(self) -> bool:
        return bool(self.race_position & 0x80)

    @property
    def race_position_value(self) -> int:
        return self.race_position & 0x7F

    @property
    def sector_index(self) -> int:
        """Setor 0, 1 ou 2. Os bits superiores são precisão extra de posição."""
        return self.sector & 0x03

    @property
    def is_lap_invalidated(self) -> bool:
        return bool(self.race_state & 0x80)


@dataclass
class TimingsPacket:
    header: PacketHeader
    num_participants: int
    participants_changed_timestamp: int
    event_time_remaining: float
    split_time_ahead: float
    split_time_behind: float
    split_time: float
    participants: list[ParticipantInfo]
    local_participant_index: int

    def local_participant(self) -> Optional[ParticipantInfo]:
        """Retorna dados do jogador local, se houver."""
        idx = self.local_participant_index
        if 0 <= idx < len(self.participants):
            return self.participants[idx]
        return None


def parse_timings(data: bytes) -> Optional[TimingsPacket]:
    """Parseia um pacote sTimingsData (1059 bytes)."""
    if len(data) < TIMINGS_PACKET_SIZE:
        return None

    header = PacketHeader.unpack(data)

    # offset 12: signed char num_participants
    # offset 13: uint32 timestamp
    # offset 17-29: 4 floats (event_time_remaining, split_ahead, split_behind, split)
    (num_participants, participants_changed_timestamp,
     event_time_remaining, split_time_ahead,
     split_time_behind, split_time) = struct.unpack_from("<bIffff", data, 12)

    # offset 33: array de 32 x sParticipantInfo (32 bytes cada = 1024 bytes)
    participants = []
    for i in range(32):
        offset = 33 + i * _PARTICIPANT_INFO_SIZE
        fields = _PARTICIPANT_INFO_STRUCT.unpack_from(data, offset)
        participants.append(ParticipantInfo(*fields))

    # offset 1057: uint16 local_participant_index
    local_participant_index, = struct.unpack_from("<H", data, 1057)

    return TimingsPacket(
        header=header,
        num_participants=num_participants,
        participants_changed_timestamp=participants_changed_timestamp,
        event_time_remaining=event_time_remaining,
        split_time_ahead=split_time_ahead,
        split_time_behind=split_time_behind,
        split_time=split_time,
        participants=participants,
        local_participant_index=local_participant_index,
    )


# ----------------------------------------------------------------------------
# sRaceData (packet_type = 1, 308 bytes) - parse parcial (só o essencial)
# ----------------------------------------------------------------------------

@dataclass
class RaceDataPacket:
    header: PacketHeader
    world_fastest_lap_time: float
    personal_fastest_lap_time: float
    track_length: float
    track_location: str
    track_variation: str


def parse_race_data(data: bytes) -> Optional[RaceDataPacket]:
    if len(data) < RACE_DATA_PACKET_SIZE:
        return None

    header = PacketHeader.unpack(data)
    world_best, personal_best = struct.unpack_from("<ff", data, 12)
    track_length, = struct.unpack_from("<f", data, 44)

    # char[64] em offset 48 e 112. Trim em null-terminator.
    track_location = data[48:48+64].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    track_variation = data[112:112+64].split(b"\x00", 1)[0].decode("utf-8", errors="replace")

    return RaceDataPacket(
        header=header,
        world_fastest_lap_time=world_best,
        personal_fastest_lap_time=personal_best,
        track_length=track_length,
        track_location=track_location,
        track_variation=track_variation,
    )


# ----------------------------------------------------------------------------
# sGameStateData (packet_type = 4, 24 bytes)
# ----------------------------------------------------------------------------

@dataclass
class GameStatePacket:
    header: PacketHeader
    build_version: int
    game_state_raw: int        # primeiros 3 bits = game state, próximos 3 = session state
    ambient_temp_c: int
    track_temp_c: int
    rain_density: int          # 0-255
    snow_density: int
    wind_speed: int
    wind_direction_x: int
    wind_direction_y: int

    @property
    def game_state(self) -> int:
        """0=Ingame_Playing, 1=Ingame_InMenu_Time_Ticking, 2=Ingame_InMenu_Time_Paused, 3=Ingame_Replay, 4=Menu/FE."""
        return self.game_state_raw & 0x07

    @property
    def session_state(self) -> int:
        """0=Invalid, 1=Practice, 2=Test, 3=Qualify, 4=Formation_Lap, 5=Race, 6=TimeAttack."""
        return (self.game_state_raw >> 3) & 0x07


def parse_game_state(data: bytes) -> Optional[GameStatePacket]:
    if len(data) < GAME_STATE_PACKET_SIZE:
        return None

    header = PacketHeader.unpack(data)
    # offset 12: uint16 build_version
    # offset 14: 1 byte de padding? Não. A spec mostra mGameState em offset 15.
    # Atenção: entre 14 e 15 há um byte de padding implícito (build_version é short alinhado,
    # mas depois vem char em offset 15 na spec). Vamos seguir offsets da spec ao pé da letra.
    build_version, = struct.unpack_from("<H", data, 12)
    # offsets 15..22 conforme spec
    (game_state_raw, ambient, track, rain, snow,
     wind_speed, wind_x, wind_y) = struct.unpack_from("<bbbBBbbb", data, 15)

    return GameStatePacket(
        header=header,
        build_version=build_version,
        game_state_raw=game_state_raw,
        ambient_temp_c=ambient,
        track_temp_c=track,
        rain_density=rain,
        snow_density=snow,
        wind_speed=wind_speed,
        wind_direction_x=wind_x,
        wind_direction_y=wind_y,
    )


# ----------------------------------------------------------------------------
# sParticipantVehicleNamesData (packet_type = 8) — nome e classe de cada carro
# Estrutura (packed, sem padding):
#   PacketBase (12 bytes)
#   sVehicleInfo[16]:
#     unsigned short mIndex   (2)
#     unsigned int   mClass   (4)
#     char           mName[64](64)
#   = 70 bytes/veículo × 16 = 1120
# Total: 1132 bytes.
# ----------------------------------------------------------------------------

VEHICLE_NAMES_PACKET_SIZE = 1132
VEHICLE_INFO_SIZE = 70
VEHICLES_PER_PACKET = 16


@dataclass
class VehicleInfo:
    index: int
    class_id: int
    name: str


@dataclass
class ParticipantVehicleNamesPacket:
    header: PacketHeader
    vehicles: list[VehicleInfo]


def _decode_cstr(raw: bytes) -> str:
    """Decodifica char[] truncando em NUL e usando UTF-8 com fallback latin-1."""
    nul = raw.find(b"\x00")
    if nul >= 0:
        raw = raw[:nul]
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace").strip()


def parse_participant_vehicle_names(data: bytes) -> Optional[ParticipantVehicleNamesPacket]:
    if len(data) < VEHICLE_NAMES_PACKET_SIZE:
        return None
    header = PacketHeader.unpack(data)
    vehicles: list[VehicleInfo] = []
    base = HEADER_SIZE
    for i in range(VEHICLES_PER_PACKET):
        off = base + i * VEHICLE_INFO_SIZE
        idx, cls = struct.unpack_from("<HI", data, off)
        name = _decode_cstr(data[off + 6: off + 70])
        if name:
            vehicles.append(VehicleInfo(index=idx, class_id=cls, name=name))
    return ParticipantVehicleNamesPacket(header=header, vehicles=vehicles)


# ----------------------------------------------------------------------------
# sVehicleClassNamesData (packet_type = 8, mas tamanho diferente) — nomes das classes
# Estrutura:
#   PacketBase (12)
#   sClassInfo[60]:
#     unsigned int mClassIndex (4)
#     char         mName[20]   (20)
#   = 24 × 60 = 1440
#   unsigned int sCurrentClassIndex (4)
# Total: 1456 bytes.
# ----------------------------------------------------------------------------

VEHICLE_CLASS_NAMES_PACKET_SIZE = 1456
CLASS_INFO_SIZE = 24
CLASSES_PER_PACKET = 60


@dataclass
class VehicleClassInfo:
    class_id: int
    name: str


@dataclass
class VehicleClassNamesPacket:
    header: PacketHeader
    classes: list[VehicleClassInfo]


def parse_vehicle_class_names(data: bytes) -> Optional[VehicleClassNamesPacket]:
    if len(data) < VEHICLE_CLASS_NAMES_PACKET_SIZE:
        return None
    header = PacketHeader.unpack(data)
    classes: list[VehicleClassInfo] = []
    base = HEADER_SIZE
    for i in range(CLASSES_PER_PACKET):
        off = base + i * CLASS_INFO_SIZE
        (cls_idx,) = struct.unpack_from("<I", data, off)
        name = _decode_cstr(data[off + 4: off + 24])
        if name:
            classes.append(VehicleClassInfo(class_id=cls_idx, name=name))
    return VehicleClassNamesPacket(header=header, classes=classes)


# ----------------------------------------------------------------------------
# Dispatcher: recebe bytes, decide tipo e parseia
# ----------------------------------------------------------------------------

def parse_packet(data: bytes):
    """
    Dispatcher principal. Recebe os bytes crus do socket e retorna o dataclass
    correspondente, ou None se o tipo não for suportado no MVP.
    """
    if len(data) < HEADER_SIZE:
        return None

    try:
        header = PacketHeader.unpack(data)
    except struct.error:
        return None

    ptype = header.packet_type

    try:
        if ptype == PacketType.CAR_PHYSICS:
            return parse_telemetry(data)
        elif ptype == PacketType.TIMINGS:
            return parse_timings(data)
        elif ptype == PacketType.RACE_DEFINITION:
            return parse_race_data(data)
        elif ptype == PacketType.GAME_STATE:
            return parse_game_state(data)
        elif ptype == PacketType.PARTICIPANT_VEHICLE_NAMES:
            # Mesmo packet_type=8 carrega 2 estruturas distintas, diferenciadas
            # pelo tamanho: 1132 = ParticipantVehicleNames, 1456 = VehicleClassNames
            if len(data) >= VEHICLE_CLASS_NAMES_PACKET_SIZE:
                return parse_vehicle_class_names(data)
            if len(data) >= VEHICLE_NAMES_PACKET_SIZE:
                return parse_participant_vehicle_names(data)
            return None
        else:
            return None
    except struct.error:
        return None
