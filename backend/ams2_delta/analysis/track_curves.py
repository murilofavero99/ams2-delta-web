"""
Mapeamento de curvas por pista.

Cada pista tem um padrão de curvas conhecido. Ao detectar uma curva,
fazemos match com a posição na volta pra identificar qual curva é.

Exemplo Montreal:
  0-500m: Curva 1 (Turn 1-2, chicane inicial)
  500-800m: Curva 2 (Turn 3)
  ...
"""
from __future__ import annotations

from dataclasses import dataclass

# Mapeamento de curvas por pista
# Cada entrada: (distance_m_start, distance_m_end, nome_descritivo)
TRACK_CURVES = {
    "Interlagos": [
        (0, 200, "Reta dos Boxes"),
        (200, 500, "S do Senna (Curvas 1-2)"),
        (500, 800, "Curva do Sol (Curva 3)"),
        (800, 1200, "Reta Oposta"),
        (1200, 1600, "Descida do Lago (Curvas 4-5-6-7)"),
        (1600, 2100, "Ferradura (Curvas 8-9)"),
        (2100, 2500, "Pinheirinho (Curva 10)"),
        (2500, 2800, "Bico de Pato (Curva 11)"),
        (2800, 3200, "Mergulho (Curvas 12-13)"),
        (3200, 3700, "Junção (Curvas 14-15)"),
        (3700, 4309, "Subida dos Boxes"),
    ],
    "Montreal": [
        (0, 350, "Chicane Inicial (Turn 1-2)"),
        (350, 650, "Curva 2 (Turn 3)"),
        (650, 950, "Curva 3 (Turn 4)"),
        (950, 1300, "Chicane Turn 5-6"),
        (1300, 1800, "Reta Principal"),
        (1800, 2150, "Curva 5 (Turn 8)"),
        (2150, 2500, "Chicane Turn 9-10"),
        (2500, 2900, "Curva 6 (Turn 11)"),
        (2900, 3300, "Curva 7 (Turn 12)"),
        (3300, 3700, "Chicane Turn 13-14"),
        (3700, 4322, "Reta de chegada"),
    ],
    "Silverstone": [
        (0, 400, "Copse"),
        (400, 700, "Maggotts"),
        (700, 1000, "Becketts"),
        (1000, 1400, "Chapel"),
        (1400, 1800, "Stowe"),
        (1800, 2200, "Vale"),
        (2200, 2600, "Club"),
        (2600, 3200, "Abbey"),
        (3200, 3600, "Luffield"),
        (3600, 4000, "Woodcote"),
    ],
    "Spa": [
        (0, 500, "Eau Rouge / Raidillon"),
        (500, 1000, "Kemmel Straight"),
        (1000, 1400, "Les Combes"),
        (1400, 1800, "Malmedy"),
        (1800, 2300, "Stavelot"),
        (2300, 2800, "Blanchimont"),
        (2800, 3200, "Pouhon"),
        (3200, 3600, "Fagnes"),
        (3600, 4200, "Masta Chicane"),
    ],
    "Suzuka": [
        (0, 400, "T1 (First Curve)"),
        (400, 800, "130R"),
        (800, 1200, "Spoon Curve"),
        (1200, 1600, "Chicane"),
        (1600, 2000, "200R"),
        (2000, 2400, "Hairpin"),
        (2400, 2800, "Snake"),
        (2800, 3200, "Degner"),
        (3200, 3600, "Chapelle"),
        (3600, 4000, "First Sector"),
    ],
    "Monza": [
        (0, 300, "Curva Grande"),
        (300, 700, "Rettifilo del Rettifilo"),
        (700, 1000, "Ascari"),
        (1000, 1400, "Roggia"),
        (1400, 1800, "Parabolica"),
        (1800, 2200, "Rettifilo"),
        (2200, 2600, "Lesmo 1"),
        (2600, 3000, "Lesmo 2"),
        (3000, 3400, "Variante Ascari"),
    ],
    "Nürburgring": [
        (0, 400, "Curva 1"),
        (400, 800, "Curva 2"),
        (800, 1200, "Curva 3"),
        (1200, 1600, "Curva 4"),
        (1600, 2000, "Curva 5"),
        (2000, 2400, "Reta Principal"),
        (2400, 2800, "Curva 6"),
        (2800, 3200, "Curva 7"),
        (3200, 3600, "Chicane Final"),
    ],
}

# Padrão fallback se pista não estiver no mapa
DEFAULT_TRACK_CURVES = [
    (i * 400, (i + 1) * 400, f"Curva {i+1}")
    for i in range(15)
]


def get_curve_name(track_location: str, track_variation: str,
                   distance_m: float) -> str:
    """
    Retorna o nome da curva para uma posição na pista.

    Args:
        track_location: Nome da pista (ex: "Montreal")
        track_variation: Variação (ex: "Montreal_Modern")
        distance_m: Distância na volta em metros

    Returns:
        Nome descritivo da curva (ex: "Chicane Inicial (Turn 1-2)")
    """
    # Tenta usar track_location direto
    curves_list = TRACK_CURVES.get(track_location)

    # Se não encontrou, tenta extrair do track_variation
    if not curves_list:
        base_track = track_variation.split("_")[0] if track_variation else track_location
        curves_list = TRACK_CURVES.get(base_track)

    # Se ainda não achou, usa padrão
    if not curves_list:
        curves_list = DEFAULT_TRACK_CURVES

    # Encontra qual curva corresponde à distância
    for dist_start, dist_end, name in curves_list:
        if dist_start <= distance_m < dist_end:
            return name

    # Se passou de todas, é reta final
    return "Reta de Chegada"


def label_curves_by_track(curves: list, track_location: str,
                          track_variation: str) -> list:
    """
    Recebe lista de curvas detectadas e adiciona nomes reais da pista.

    Args:
        curves: lista de Curve objects com distance_start_m
        track_location: "Montreal", "Silverstone", etc.
        track_variation: "Montreal_Modern", etc.

    Returns:
        Mesma lista de curves, mas com .name atualizado
    """
    for curve in curves:
        # Nome baseado na distância do início da curva
        curve.name = get_curve_name(track_location, track_variation,
                                    curve.distance_start_m)

    return curves
