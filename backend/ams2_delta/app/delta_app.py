"""
AMS2 Delta — app Streamlit multi-página.

Rodar:
    python -m streamlit run src/ams2_delta/app/delta_app.py

Estrutura:
    delta_app.py        -> tela inicial, lista de sessões disponíveis
    pages/1_Mapa.py     -> mapa visual da pista (análise principal)
    pages/2_Graficos.py -> gráficos de delta e traços sobrepostos

O Streamlit descobre as páginas automaticamente pela pasta pages/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ams2_delta.analysis.session import format_lap_time, list_sessions, load_session


st.set_page_config(
    page_title="AMS2 Delta",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { max-width: 1200px; }
    h1 { margin-bottom: 0.5rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("🏁 AMS2 Delta")
st.caption("Análise de telemetria pós-sessão para Automobilista 2")

st.markdown("""
Bem-vindo. Este app analisa as sessões de telemetria gravadas com o listener UDP.
Use o menu à esquerda para navegar:

- **🗺️ Mapa** — traçado da pista colorido por velocidade, marchas ou delta,
  com os pontos de freada destacados. Ideal para ver rapidamente onde você
  está ganhando ou perdendo tempo.
- **📊 Gráficos** — delta acumulado e traços sobrepostos de velocidade, acelerador,
  freio e volante. Ideal para análise técnica detalhada.
""")

DEFAULT_SESSIONS_DIR = Path("sessions").resolve()

with st.sidebar:
    st.header("Sessões")
    sessions_dir = Path(
        st.text_input("Pasta", value=str(DEFAULT_SESSIONS_DIR))
    ).expanduser().resolve()

session_dirs = list_sessions(sessions_dir)

if not session_dirs:
    st.warning(f"Nenhuma sessão encontrada em `{sessions_dir}`.")
    st.markdown("""
    Para gerar uma sessão, abra o AMS2 (com UDP Project CARS 2, Frequência 1) e rode:

    ```bash
    python -m ams2_delta.udp.listener --name nome_da_sessao
    ```

    Rode durante sua pilotagem e aperte Ctrl+C quando terminar.
    """)
    st.stop()

st.markdown(f"### {len(session_dirs)} sessões disponíveis")

rows = []
for sdir in session_dirs[:15]:
    try:
        s = load_session(sdir)
        fastest = s.fastest_lap()
        rows.append({
            "Sessão": sdir.name,
            "Pista": s.metadata.track_location or "—",
            "Variação": s.metadata.track_variation or "—",
            "Voltas válidas": len(s.valid_laps()),
            "Melhor volta": format_lap_time(fastest.lap_time_s) if fastest else "—",
            "Samples": s.metadata.num_samples,
        })
    except Exception as e:
        rows.append({
            "Sessão": sdir.name, "Pista": f"[ERRO: {e}]",
            "Variação": "", "Voltas válidas": 0, "Melhor volta": "—", "Samples": 0,
        })

st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

st.info("👈 Escolha **Mapa** no menu à esquerda para começar a análise.")
