"""
Página principal: Mapa da pista.

Reconstruir o traçado de Montreal (ou qualquer pista) a partir dos pontos
(world_x, world_z) gravados, com visualização colorida pela variável que
o usuário escolher. Destaque especial pros pontos de freada.

Rodar:
    python -m streamlit run src/ams2_delta/app/delta_app.py

(o arquivo /app/delta_app.py é o ponto de entrada; este "1_Mapa.py" é
descoberto automaticamente como primeira página via convenção Streamlit)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ams2_delta.analysis.session import (
    BrakingZone, compare_braking_points, compute_delta, detect_braking_zones,
    format_lap_time, list_sessions, load_session,
)


# ===========================================================================
# Config e estilo
# ===========================================================================

st.set_page_config(
    page_title="AMS2 Delta — Mapa",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS enxuto pra deixar o mapa ocupar a tela
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 0; max-width: 100%; }
    [data-testid="stMetricValue"] { font-size: 1.3rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.3rem; }
</style>
""", unsafe_allow_html=True)

st.title("🏁 AMS2 Delta — Mapa de Pista")


# ===========================================================================
# Sidebar: seleção de sessão e voltas
# ===========================================================================

DEFAULT_SESSIONS_DIR = Path("sessions").resolve()

with st.sidebar:
    st.header("Sessão")

    sessions_dir = Path(
        st.text_input("Pasta de sessões", value=str(DEFAULT_SESSIONS_DIR))
    ).expanduser().resolve()

    session_dirs = list_sessions(sessions_dir)
    if not session_dirs:
        st.error(f"Nenhuma sessão em {sessions_dir}.\n\n"
                 "Rode:\n`python -m ams2_delta.udp.listener --name teste`")
        st.stop()

    session_choice = st.selectbox(
        "Sessão",
        options=session_dirs,
        format_func=lambda p: p.name,
    )

session = load_session(session_choice)

with st.sidebar:
    st.markdown("---")
    st.header("Voltas")

    valid_laps = session.valid_laps()
    if not valid_laps:
        st.warning("Nenhuma volta válida nesta sessão.")
        st.stop()

    lap_nums = [lap.lap_number for lap in valid_laps]

    def fmt_lap(n: int) -> str:
        lap = next(l for l in valid_laps if l.lap_number == n)
        fastest = session.fastest_lap()
        mark = " ⭐" if (fastest and lap.lap_number == fastest.lap_number) else ""
        return f"Volta {n} — {format_lap_time(lap.lap_time_s)}{mark}"

    target_lap_num = st.selectbox(
        "Volta para analisar", options=lap_nums,
        index=0, format_func=fmt_lap,
    )

    compare_enabled = len(valid_laps) >= 2
    use_reference = compare_enabled and st.checkbox(
        "Comparar com volta de referência", value=True
    )

    ref_lap_num = None
    if use_reference:
        # Default: volta mais rápida, ou a primeira que não seja a alvo
        fastest = session.fastest_lap()
        default_ref = fastest.lap_number if fastest and fastest.lap_number != target_lap_num else \
                      next((n for n in lap_nums if n != target_lap_num), lap_nums[0])
        ref_options = [n for n in lap_nums if n != target_lap_num]
        ref_index = ref_options.index(default_ref) if default_ref in ref_options else 0
        ref_lap_num = st.selectbox(
            "Volta de referência", options=ref_options,
            index=ref_index, format_func=fmt_lap,
        )

    st.markdown("---")
    st.header("Visualização")

    view_mode = st.radio(
        "Colorir mapa por",
        options=["Velocidade", "Zonas de freada", "Marchas", "Delta vs ref"],
        index=0,
    )

    if view_mode == "Delta vs ref" and not use_reference:
        st.info("Ative 'Comparar com referência' para ver o delta no mapa")
        view_mode = "Velocidade"

    st.markdown("---")
    st.header("Faixas de velocidade")
    st.caption("Limites para o modo 'Velocidade' (km/h)")
    spd_1 = st.slider("🔴 Vermelho abaixo de", 20, 100, 60, 5,
                       help="Abaixo desse valor = vermelho (lento)")
    spd_2 = st.slider("🟠 Laranja abaixo de", spd_1 + 10, 200, 110, 5,
                       help="Entre vermelho e amarelo")
    spd_3 = st.slider("🟡 Amarelo abaixo de", spd_2 + 10, 250, 160, 5,
                       help="Entre laranja e verde claro")
    spd_4 = st.slider("🟢 Verde claro abaixo de", spd_3 + 10, 320, 210, 5,
                       help="Acima desse valor = verde escuro (rápido)")

    st.markdown("---")
    st.header("Detecção de freadas")
    brake_threshold = st.slider("Limite de pressão (%)", 5, 50, 20, 5,
                                help="Acima desse valor conta como 'freando'")
    min_brake_duration = st.slider("Duração mínima (m)", 5, 50, 15, 5,
                                   help="Freadas mais curtas que isso são ignoradas")


# ===========================================================================
# Carrega telemetria das voltas selecionadas
# ===========================================================================

target_df = session.lap_telemetry(target_lap_num)
ref_df = session.lap_telemetry(ref_lap_num) if ref_lap_num is not None else None

if target_df.empty:
    st.error("Volta alvo sem telemetria.")
    st.stop()

# ===========================================================================
# Header metrics
# ===========================================================================

target_lap_obj = next(l for l in valid_laps if l.lap_number == target_lap_num)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Pista", session.metadata.track_location or "—")
col2.metric("Variação", session.metadata.track_variation or "—")
col3.metric("Tempo", format_lap_time(target_lap_obj.lap_time_s))
col4.metric("Vel. máx.", f"{target_df['speed_kmh'].max():.0f} km/h")
col5.metric("Samples", f"{len(target_df)}")

# ===========================================================================
# Mapa principal
# ===========================================================================

def build_hover_text(df: pd.DataFrame) -> list[str]:
    """Tooltip amigável mostrando estado do carro em cada ponto."""
    return [
        f"<b>Dist:</b> {d:.0f}m<br>"
        f"<b>Vel:</b> {v:.1f} km/h<br>"
        f"<b>Marcha:</b> {g}<br>"
        f"<b>RPM:</b> {r}<br>"
        f"<b>Thr:</b> {t:.0f}%  <b>Brk:</b> {b:.0f}%"
        for d, v, g, r, t, b in zip(
            df["current_lap_distance"], df["speed_kmh"], df["gear"], df["rpm"],
            df["throttle_pct"], df["brake_pct"]
        )
    ]


def _add_discrete_traces(fig: go.Figure, df: pd.DataFrame,
                         hover: list[str], bands: list[dict]) -> None:
    """
    Desenha o traçado como múltiplos traces, um por faixa de cor discreta.

    Cada band é um dict com:
        label  : str  — texto que aparece na legenda (ex.: "< 60 km/h")
        color  : str  — hex da cor
        mask   : pd.Series[bool] — quais linhas do df pertencem a essa faixa
    """
    for band in bands:
        sub = df[band["mask"]]
        if sub.empty:
            continue
        sub_hover = [hover[i] for i in sub.index]
        fig.add_trace(go.Scatter(
            x=sub["world_x"],
            y=sub["world_z"],
            mode="markers",
            marker=dict(size=5, color=band["color"]),
            text=sub_hover,
            hovertemplate="%{text}<extra></extra>",
            name=band["label"],
            legendgroup=band["label"],
        ))


def make_track_figure(df: pd.DataFrame, mode: str,
                      delta_df: pd.DataFrame | None = None,
                      speed_limits: tuple = (60, 110, 160, 210)) -> go.Figure:
    """
    Cria a figura do mapa com cores DISCRETAS por faixa — cada banda de
    velocidade (ou marcha, ou freada) tem uma cor sólida única, sem gradiente.

    Isso torna a leitura muito mais imediata: verde = rápido, vermelho = lento,
    sem precisar interpretar escala de cor.
    """
    fig = go.Figure()
    hover = build_hover_text(df)

    if mode == "Velocidade":
        s1, s2, s3, s4 = speed_limits
        # 5 faixas discretas calibradas pelos sliders da sidebar
        bands = [
            {
                "label": f"< {s1} km/h",
                "color": "#ef4444",   # vermelho vivo
                "mask": df["speed_kmh"] < s1,
            },
            {
                "label": f"{s1}–{s2} km/h",
                "color": "#f97316",   # laranja
                "mask": (df["speed_kmh"] >= s1) & (df["speed_kmh"] < s2),
            },
            {
                "label": f"{s2}–{s3} km/h",
                "color": "#eab308",   # amarelo
                "mask": (df["speed_kmh"] >= s2) & (df["speed_kmh"] < s3),
            },
            {
                "label": f"{s3}–{s4} km/h",
                "color": "#84cc16",   # verde claro
                "mask": (df["speed_kmh"] >= s3) & (df["speed_kmh"] < s4),
            },
            {
                "label": f"> {s4} km/h",
                "color": "#22c55e",   # verde escuro
                "mask": df["speed_kmh"] >= s4,
            },
        ]
        _add_discrete_traces(fig, df, hover, bands)

    elif mode == "Zonas de freada":
        # 3 faixas: sem freio / freio leve / freio forte
        bands = [
            {
                "label": "Sem freio (< 20%)",
                "color": "#475569",   # cinza escuro — acelerando / coasting
                "mask": df["brake_pct"] < 20,
            },
            {
                "label": "Freio leve (20–60%)",
                "color": "#f97316",   # laranja — trail braking, entrada de curva
                "mask": (df["brake_pct"] >= 20) & (df["brake_pct"] < 60),
            },
            {
                "label": "Freio forte (> 60%)",
                "color": "#ef4444",   # vermelho — freada a fundo
                "mask": df["brake_pct"] >= 60,
            },
        ]
        _add_discrete_traces(fig, df, hover, bands)

    elif mode == "Marchas":
        # Uma cor fixa por marcha — fácil de memorizar
        gear_palette = {
            0:  ("#94a3b8", "Neutro"),
            1:  ("#ef4444", "1ª"),
            2:  ("#f97316", "2ª"),
            3:  ("#eab308", "3ª"),
            4:  ("#84cc16", "4ª"),
            5:  ("#22c55e", "5ª"),
            6:  ("#06b6d4", "6ª"),
            7:  ("#6366f1", "7ª"),
            -1: ("#7c3aed", "Ré"),
        }
        for gear_val, (color, label) in gear_palette.items():
            mask = df["gear"] == gear_val
            if not mask.any():
                continue
            sub = df[mask]
            sub_hover = [hover[i] for i in sub.index]
            fig.add_trace(go.Scatter(
                x=sub["world_x"], y=sub["world_z"],
                mode="markers",
                marker=dict(size=5, color=color),
                text=sub_hover,
                hovertemplate="%{text}<extra></extra>",
                name=label, legendgroup=label,
            ))

    else:  # Delta vs ref
        if delta_df is None or delta_df.empty:
            # Fallback: velocidade se não tiver referência
            bands = [
                {"label": "< 60 km/h",   "color": "#ef4444", "mask": df["speed_kmh"] < 60},
                {"label": "60–110 km/h",  "color": "#f97316", "mask": (df["speed_kmh"] >= 60) & (df["speed_kmh"] < 110)},
                {"label": "110–160 km/h", "color": "#eab308", "mask": (df["speed_kmh"] >= 110) & (df["speed_kmh"] < 160)},
                {"label": "160–210 km/h", "color": "#84cc16", "mask": (df["speed_kmh"] >= 160) & (df["speed_kmh"] < 210)},
                {"label": "> 210 km/h",   "color": "#22c55e", "mask": df["speed_kmh"] >= 210},
            ]
            _add_discrete_traces(fig, df, hover, bands)
        else:
            # Delta: 5 faixas simétricas — azul ganhando, branco neutro, vermelho perdendo
            delta_interp = np.interp(
                df["current_lap_distance"].values,
                delta_df["distance_m"].values,
                delta_df["delta_s"].values,
            )
            delta_s = pd.Series(delta_interp, index=df.index)
            bands = [
                {
                    "label": "Ganhando > 0.5s",
                    "color": "#1d4ed8",    # azul forte
                    "mask": delta_s < -0.5,
                },
                {
                    "label": "Ganhando 0–0.5s",
                    "color": "#60a5fa",    # azul claro
                    "mask": (delta_s >= -0.5) & (delta_s < 0),
                },
                {
                    "label": "Neutro (±0.1s)",
                    "color": "#e2e8f0",    # quase branco
                    "mask": (delta_s >= -0.1) & (delta_s < 0.1),
                },
                {
                    "label": "Perdendo 0–0.5s",
                    "color": "#fb923c",    # laranja
                    "mask": (delta_s >= 0.1) & (delta_s < 0.5),
                },
                {
                    "label": "Perdendo > 0.5s",
                    "color": "#dc2626",    # vermelho forte
                    "mask": delta_s >= 0.5,
                },
            ]
            _add_discrete_traces(fig, df, hover, bands)

    return fig


def add_braking_markers(fig: go.Figure, zones: list[BrakingZone],
                        color: str = "#dc2626", symbol: str = "circle",
                        name: str = "Início de freada") -> None:
    """Adiciona marcadores grandes nos pontos onde o piloto iniciou cada freada."""
    if not zones:
        return

    fig.add_trace(go.Scatter(
        x=[z.world_x_start for z in zones],
        y=[z.world_z_start for z in zones],
        mode="markers+text",
        marker=dict(
            size=18, color=color, symbol=symbol,
            line=dict(color="white", width=2),
        ),
        text=[str(i + 1) for i in range(len(zones))],
        textposition="middle center",
        textfont=dict(color="white", size=11, family="Arial Black"),
        hovertext=[
            f"<b>Freada #{i+1}</b><br>"
            f"Entrada: {z.speed_entry_kmh:.0f} km/h<br>"
            f"Saída: {z.speed_exit_kmh:.0f} km/h<br>"
            f"Dist: {z.distance_start_m:.0f}m na volta<br>"
            f"Pressão máx: {z.max_brake_pct:.0f}%<br>"
            f"Duração: {z.duration_m:.0f}m"
            for i, z in enumerate(zones)
        ],
        hovertemplate="%{hovertext}<extra></extra>",
        name=name,
    ))


# Detecta zonas de freada
target_zones = detect_braking_zones(
    target_df, threshold_pct=brake_threshold, min_duration_m=min_brake_duration
)

# Calcula delta se tiver referência
delta_df = None
if ref_df is not None and not ref_df.empty:
    delta_df = compute_delta(
        target_df, ref_df,
        track_length_m=session.metadata.track_length_m or None,
        step_m=1.0,
    )

# Monta o mapa
fig = make_track_figure(target_df, view_mode, delta_df=delta_df,
                        speed_limits=(spd_1, spd_2, spd_3, spd_4))

# Adiciona marcadores de freada (sempre visíveis, em qualquer modo)
add_braking_markers(fig, target_zones)

# Se tem referência e NÃO está no modo delta, mostra também as freadas da ref
# com símbolo diferente (fantasma)
if ref_df is not None and view_mode != "Delta vs ref":
    ref_zones = detect_braking_zones(
        ref_df, threshold_pct=brake_threshold, min_duration_m=min_brake_duration
    )
    add_braking_markers(fig, ref_zones, color="#3b82f6", symbol="diamond-open",
                        name="Freadas referência")

# Primeiro ponto da volta com estrela verde (linha de largada / start/finish)
if len(target_df) > 0:
    fig.add_trace(go.Scatter(
        x=[target_df["world_x"].iloc[0]],
        y=[target_df["world_z"].iloc[0]],
        mode="markers",
        marker=dict(size=22, color="#22c55e", symbol="star",
                    line=dict(color="white", width=2)),
        hovertext=["Largada / linha de chegada"],
        hovertemplate="%{hovertext}<extra></extra>",
        name="Start/Finish",
    ))

fig.update_layout(
    height=700,
    xaxis=dict(scaleanchor="y", scaleratio=1, showgrid=False, zeroline=False,
               showticklabels=False, title=""),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor="#0f172a",
    paper_bgcolor="#0f172a",
    font=dict(color="#e2e8f0"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
        bgcolor="rgba(15, 23, 42, 0.8)", bordercolor="#334155", borderwidth=1,
    ),
    hoverlabel=dict(bgcolor="#1e293b", font_size=13, font_color="#e2e8f0"),
)

st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# Análise de freadas (se tiver referência)
# ===========================================================================

if ref_df is not None and target_zones:
    ref_zones = detect_braking_zones(
        ref_df, threshold_pct=brake_threshold, min_duration_m=min_brake_duration
    )

    st.markdown("### 🛑 Análise das freadas")

    if ref_zones:
        comparisons = compare_braking_points(target_zones, ref_zones)

        if comparisons:
            # Monta tabela visual
            rows = []
            for c in comparisons:
                diff = c["diff_m"]
                if diff > 5:
                    marker = "🔴 freou tarde"
                elif diff < -5:
                    marker = "🟢 freou cedo"
                else:
                    marker = "🟡 no ponto"

                rows.append({
                    "Curva": f"#{c['curve_num']}",
                    "Status": marker,
                    "Sua freada (m)": f"{c['target_distance_m']:.0f}",
                    "Referência (m)": f"{c['ref_distance_m']:.0f}",
                    "Diferença": f"{diff:+.0f}m",
                    "Vel. entrada alvo": f"{c['target_speed_entry']:.0f} km/h",
                    "Vel. entrada ref": f"{c['ref_speed_entry']:.0f} km/h",
                })

            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            # Resumo numérico
            avg_diff = np.mean([c["diff_m"] for c in comparisons])
            late_count = sum(1 for c in comparisons if c["diff_m"] > 5)
            early_count = sum(1 for c in comparisons if c["diff_m"] < -5)

            sum1, sum2, sum3 = st.columns(3)
            sum1.metric("Curvas analisadas", len(comparisons))
            sum2.metric("Freou tarde em", f"{late_count} curvas",
                        delta=f"média {avg_diff:+.0f}m")
            sum3.metric("Freou cedo em", f"{early_count} curvas")

            st.caption("💡 Diferença **positiva** = você freou **depois** da referência "
                       "(mais tarde). **Negativa** = freou antes. Freadas 'no ponto' "
                       "estão dentro de ±5m da referência.")
        else:
            st.info("Não consegui parear as freadas das duas voltas. "
                    "Talvez as trajetórias estejam muito diferentes.")
    else:
        st.info("A volta de referência não teve freadas detectadas acima do limite.")

elif target_zones:
    st.markdown("### 🛑 Freadas detectadas nesta volta")
    rows = []
    for i, z in enumerate(target_zones):
        rows.append({
            "Curva": f"#{i+1}",
            "Distância na volta": f"{z.distance_start_m:.0f}m",
            "Vel. entrada": f"{z.speed_entry_kmh:.0f} km/h",
            "Vel. saída": f"{z.speed_exit_kmh:.0f} km/h",
            "Delta vel.": f"{z.speed_entry_kmh - z.speed_exit_kmh:.0f} km/h",
            "Pressão máx": f"{z.max_brake_pct:.0f}%",
            "Duração": f"{z.duration_m:.0f}m",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("💡 Para ver onde você está freando cedo/tarde vs uma referência, "
               "marque 'Comparar com volta de referência' no painel à esquerda.")

# ===========================================================================
# Legenda
# ===========================================================================

with st.expander("ℹ️ Como ler este mapa"):
    st.markdown("""
    - **⭐ Estrela verde**: linha de largada/chegada (início da volta)
    - **🔴 Círculos vermelhos numerados**: onde VOCÊ começou a frear em cada curva
    - **💎 Diamantes azuis**: onde a referência começou a frear (quando ativo)
    - **Traço colorido**: seu carro em cada ponto da pista. A cor depende do modo:
      - **Velocidade**: azul = lento, vermelho = rápido
      - **Zonas de freada**: cinza = sem freio, amarelo→vermelho conforme a pressão
      - **Marchas**: cada marcha uma cor
      - **Delta**: azul = você está ganhando tempo aqui, vermelho = perdendo
    - **Hover em qualquer ponto**: mostra velocidade, marcha, throttle, brake, RPM
    """)
