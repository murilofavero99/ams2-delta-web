"""
Página 2 — Análise detalhada com gráficos.

Traços sobrepostos de velocidade, throttle, brake, steering + gráfico do
delta acumulado ao longo da volta. Complementa a página do Mapa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ams2_delta.analysis.session import (
    compute_delta, format_lap_time, list_sessions, load_session, summarize_delta,
)


st.set_page_config(
    page_title="AMS2 Delta — Gráficos",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Análise detalhada")

# Sidebar
DEFAULT_SESSIONS_DIR = Path("sessions").resolve()
with st.sidebar:
    st.header("Sessão")
    sessions_dir = Path(
        st.text_input("Pasta", value=str(DEFAULT_SESSIONS_DIR))
    ).expanduser().resolve()

    session_dirs = list_sessions(sessions_dir)
    if not session_dirs:
        st.error("Nenhuma sessão encontrada.")
        st.stop()

    session_choice = st.selectbox("Sessão", options=session_dirs,
                                  format_func=lambda p: p.name)

session = load_session(session_choice)

# Header metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Pista", session.metadata.track_location or "—")
c2.metric("Variação", session.metadata.track_variation or "—")
c3.metric("Extensão",
          f"{session.metadata.track_length_m:.0f} m" if session.metadata.track_length_m else "—")
c4.metric("Voltas", len(session.laps))

# Tabela de voltas
st.subheader("Voltas desta sessão")
if not session.laps:
    st.warning("Nenhuma volta registrada.")
    st.stop()

fastest = session.fastest_lap()
fastest_num = fastest.lap_number if fastest else -1
laps_table = pd.DataFrame([
    {
        "Volta": lap.lap_number,
        "Tempo": format_lap_time(lap.lap_time_s),
        "Tempo (s)": round(lap.lap_time_s, 3),
        "Válida": "✅" if not lap.invalidated else "❌",
        "Melhor": "⭐" if lap.lap_number == fastest_num else "",
    }
    for lap in session.laps
])
st.dataframe(laps_table, hide_index=True, use_container_width=True)

# Seleção de voltas
st.subheader("Comparação de voltas")
valid_laps = session.valid_laps()
if len(valid_laps) < 2:
    st.info("Você precisa de pelo menos 2 voltas válidas para comparar.")
    st.stop()

default_ref = fastest.lap_number if fastest else valid_laps[0].lap_number
lap_options = [lap.lap_number for lap in valid_laps]

colA, colB = st.columns(2)
with colA:
    target_lap_num = st.selectbox(
        "Volta alvo", options=lap_options,
        format_func=lambda n: f"Volta {n} — {format_lap_time(next(l.lap_time_s for l in valid_laps if l.lap_number == n))}",
    )
with colB:
    ref_options = [n for n in lap_options if n != target_lap_num]
    ref_index = ref_options.index(default_ref) if default_ref in ref_options else 0
    ref_lap_num = st.selectbox(
        "Referência", options=ref_options, index=ref_index,
        format_func=lambda n: f"Volta {n} — {format_lap_time(next(l.lap_time_s for l in valid_laps if l.lap_number == n))}" + (" ⭐" if n == fastest_num else ""),
    )

target_df = session.lap_telemetry(target_lap_num)
ref_df = session.lap_telemetry(ref_lap_num)
delta_df = compute_delta(target_df, ref_df,
                         track_length_m=session.metadata.track_length_m or None,
                         step_m=1.0)

if delta_df.empty:
    st.error("Falha ao calcular delta.")
    st.stop()

# Resumo
summary = summarize_delta(delta_df)
st.markdown("### Resumo")
sc = st.columns(4)
sc[0].metric("Delta final", f"{summary.get('final_delta_s', 0):+.3f} s")
sc[1].metric("Maior perda", f"{summary.get('max_loss_s', 0):+.3f} s",
             help=f"Em {summary.get('max_loss_at_m', 0):.0f}m")
sc[2].metric("Maior ganho", f"{summary.get('max_gain_s', 0):+.3f} s",
             help=f"Em {summary.get('max_gain_at_m', 0):.0f}m")
sc[3].metric("Vel. máx. alvo", f"{summary.get('max_speed_lap_kmh', 0):.0f} km/h")

# Delta acumulado
st.markdown("### Delta acumulado")
fig_delta = go.Figure()
fig_delta.add_trace(go.Scatter(
    x=delta_df["distance_m"], y=delta_df["delta_s"],
    mode="lines", name="Delta",
    line=dict(color="#e74c3c", width=2), fill="tozeroy",
))
fig_delta.add_hline(y=0, line_dash="dash", line_color="gray")
fig_delta.update_layout(
    xaxis_title="Distância na volta (m)", yaxis_title="Delta (s)",
    height=280, margin=dict(l=40, r=20, t=10, b=40), hovermode="x unified",
)
st.plotly_chart(fig_delta, use_container_width=True)

# Traços sobrepostos
st.markdown("### Traços sobrepostos")
fig = make_subplots(
    rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
    subplot_titles=("Velocidade (km/h)", "Acelerador (%)", "Freio (%)", "Volante (%)"),
    row_heights=[0.3, 0.25, 0.25, 0.2],
)

C_LAP = "#e74c3c"
C_REF = "#3b82f6"

for row, (col_lap, col_ref, title) in enumerate([
    ("speed_lap", "speed_ref", "Vel"),
    ("throttle_lap", "throttle_ref", "Thr"),
    ("brake_lap", "brake_ref", "Brk"),
    ("steering_lap", "steering_ref", "Str"),
], start=1):
    fig.add_trace(go.Scatter(
        x=delta_df["distance_m"], y=delta_df[col_lap],
        line=dict(color=C_LAP, width=1.5),
        name=f"Volta {target_lap_num}" if row == 1 else None,
        showlegend=(row == 1), legendgroup="lap",
    ), row=row, col=1)
    fig.add_trace(go.Scatter(
        x=delta_df["distance_m"], y=delta_df[col_ref],
        line=dict(color=C_REF, width=1.5),
        name=f"Referência ({ref_lap_num})" if row == 1 else None,
        showlegend=(row == 1), legendgroup="ref",
    ), row=row, col=1)

fig.update_xaxes(title_text="Distância na volta (m)", row=4, col=1)
fig.update_layout(
    height=700, margin=dict(l=40, r=20, t=40, b=40), hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig, use_container_width=True)
