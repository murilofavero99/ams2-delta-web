"""
Página 3 — Análise com IA.

Usuário escolhe entre:
  - Ollama (grátis, offline, local)
  - Claude (premium, online, melhor qualidade)

Ambos geram feedback estruturado em português com recomendações por setor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import anthropic
import numpy as np
import pandas as pd
import requests
import streamlit as st

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ams2_delta.analysis.session import (
    compute_delta, detect_braking_zones, format_lap_time, list_sessions,
    load_session, summarize_delta,
)
from ams2_delta.analysis.curve_detection import detect_curves, estimate_ideal_speed
from ams2_delta.analysis.track_curves import label_curves_by_track
from ams2_delta.app.config_ai import CLAUDE_MODEL, MODELS, OLLAMA_MODEL, OLLAMA_URL


st.set_page_config(
    page_title="AMS2 Delta — IA",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Análise com IA")
st.caption("Feedback automático sobre sua pilotagem")

# ===========================================================================
# Sidebar: Configuração de IA
# ===========================================================================

DEFAULT_SESSIONS_DIR = Path("sessions").resolve()

with st.sidebar:
    st.header("Configuração de IA")

    # Escolha do modelo
    ai_choice = st.radio(
        "Selecione o modelo",
        options=["ollama", "claude"],
        format_func=lambda x: MODELS[x]["name"],
    )

    model_info = MODELS[ai_choice]
    st.info(f"""
    **{model_info['description']}**
    
    - Velocidade: {model_info['speed']}
    - Qualidade: {model_info['quality']}
    {f"- Custo: {model_info.get('cost_estimate', 'Grátis')}" if 'cost_estimate' in model_info else ""}
    """)

    # Chave da API (só se Claude)
    claude_key = None
    if ai_choice == "claude":
        claude_key = st.text_input(
            "Chave da API Claude",
            type="password",
            help="Obtém em https://console.anthropic.com/keys — não é guardada, só usada na sessão",
        )
        if not claude_key:
            st.warning("Cole sua chave da API pra usar Claude.")

    st.markdown("---")
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

# ===========================================================================
# Carrega sessão e telemetria
# ===========================================================================

session = load_session(session_choice)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Pista", session.metadata.track_location or "—")
c2.metric("Variação", session.metadata.track_variation or "—")
c3.metric("Voltas", len(session.valid_laps()))
c4.metric("Track", f"{session.metadata.track_length_m:.0f}m" if session.metadata.track_length_m else "—")

valid_laps = session.valid_laps()
if not valid_laps:
    st.warning("Nenhuma volta válida.")
    st.stop()

fastest = session.fastest_lap()
lap_nums = [lap.lap_number for lap in valid_laps]

def fmt_lap(n: int) -> str:
    lap = next(l for l in valid_laps if l.lap_number == n)
    mark = " ⭐" if (fastest and lap.lap_number == fastest.lap_number) else ""
    return f"Volta {n} — {format_lap_time(lap.lap_time_s)}{mark}"

target_lap_num = st.selectbox("Volta para analisar", options=lap_nums,
                              format_func=fmt_lap)

target_df = session.lap_telemetry(target_lap_num)
target_lap_obj = next(l for l in valid_laps if l.lap_number == target_lap_num)

if target_df.empty:
    st.error("Sem telemetria.")
    st.stop()

# ===========================================================================
# Extração de padrões
# ===========================================================================

braking_zones = detect_braking_zones(target_df, threshold_pct=20.0,
                                     min_duration_m=15.0)

# Detecta curvas automaticamente
curves = detect_curves(target_df, min_curve_duration_m=20.0,
                       speed_change_threshold_kmh=15.0)

# Nomeia as curvas baseado na pista real
curves = label_curves_by_track(curves, session.metadata.track_location,
                               session.metadata.track_variation)

max_speed = target_df["speed_kmh"].max()
avg_speed = target_df["speed_kmh"].mean()
max_rpm = target_df["rpm"].max()
avg_throttle = target_df["throttle_pct"].mean()
avg_brake = target_df["brake_pct"].mean()

# Calcula estatísticas POR CURVA (não por setor)
curve_stats = []
for curve in curves:
    ideal_speed_data = estimate_ideal_speed(curve)
    curve_stats.append({
        "name": curve.name,
        "curve_num": curve.curve_num,
        "speed_entry": curve.speed_entry_kmh,
        "speed_apex": curve.speed_apex_kmh,
        "speed_exit": curve.speed_exit_kmh,
        "ideal_apex_speed": ideal_speed_data["ideal_speed_apex_kmh"],
        "speed_margin": ideal_speed_data["margin_kmh"],
        "recommendation": ideal_speed_data["recommendation"],
        "max_steering": curve.max_steering_pct,
        "avg_brake": curve.avg_brake_pct,
        "avg_throttle": curve.avg_throttle_pct,
        "duration_m": curve.duration_m,
    })

delta_summary = None
if len(valid_laps) >= 2:
    ref_lap_num = fastest.lap_number if fastest else valid_laps[0].lap_number
    if ref_lap_num != target_lap_num:
        ref_df = session.lap_telemetry(ref_lap_num)
        delta_df = compute_delta(target_df, ref_df,
                                 track_length_m=session.metadata.track_length_m,
                                 step_m=1.0)
        if not delta_df.empty:
            delta_summary = summarize_delta(delta_df)

# ===========================================================================
# Construção do prompt
# ===========================================================================

prompt_system = """Você é um engenheiro de automobilismo especializado em trail braking e telemetria de simuladores.
Analise a volta de um piloto em Automobilista 2 com EXPERTISE EM FRENAGEM E TIMING.

CONTEXTO DO PILOTO:
- Padrão atual: freia TARDE DEMAIS com pressão ALTA compensando
- Objetivo: aprender TRAIL BRAKING (freio progressivo que continua na curva)
- Estilo desejado: iniciar freada mais cedo, reduzir pressão, manter freio na entrada/ápice
- REFERÊNCIA: Hotlap profissional GO Setups (McLaren 720S GT3 EVO2, Montreal, 1:31.080)
  * Seu tempo: ~1:40.5
  * Gap: ~9.4 segundos (muito desse gap vem de frenagem/trail braking)

PADRÃO DO HOTLAP PROFISSIONAL (baseado em análise de Montreal):
- Freia CEDO (15-25m antes da curva) com pressão MODERADA (30-45%)
- MANTÉM freio na entrada, solta PROGRESSIVAMENTE na saída (trail braking puro)
- Resultado: entrada rápida mas controlada, margem segura, saída agressiva
- Isso permite ganho de 0.8-1.5s em FRENAGEM APENAS vs. padrão "freia tarde + pressão alta"

ESTRUCTURA OBRIGATÓRIA DA RESPOSTA:

1. RESUMO EXECUTIVO (5-6 frases):
   - Nota geral (1-10)
   - Os 3 maiores ganhos potenciais em TEMPO (com estimativa)
   - 1 ponto forte
   - Recomendação #1 para a próxima volta
   - FOCO: quantos segundos você pode ganhar só ajustando frenagem

2. ANÁLISE DETALHADA DE FRENAGEM (PRIORIDADE MÁXIMA):
   
   A. DIAGNÓSTICO GERAL vs. HOTLAP:
      - Seu padrão vs. padrão profissional: diferenças-chave
      - Problema identificado: você está TARDE e FORTE
      - Por que piora: entrada rápida força freio tardio (ciclo vicioso)
      - O profissional faz: CEDO e SUAVE (trail braking)
   
   B. ANÁLISE POR CURVA - FRENAGEM ESPECÍFICA vs. HOTLAP:
      Para CADA curva com freio:
      - Quando você INICIA freada (em metros antes da curva)
      - Quando o hotlap inicia (estimado pela dinâmica)
      - Diferença de TIMING (você está Xm tarde)
      - Sua pressão (pico e média)
      - Pressão do hotlap (geralmente 30-40%, mais baixa)
      - Ação concreta: "Inicia 20m antes com 35% (vs. seu 10m com 55%)"
      - Ganho estimado em tempo (0.2s? 0.5s?)

3. VELOCIDADE NAS CURVAS (CONTEXTO DE TRAIL BRAKING):
   - Sua entrada vs. entrada ideal (do hotlap)
   - Por que sua entrada está alta: freada muito tardia
   - Solução: freia MAIS CEDO = entrada mais lenta = menos agressivo no freio

4. THROTTLE PROGRESSÃO:
   - Quando você SOLTA o freio vs. quando APERTA o throttle
   - Padrão profissional: sobreposição de 0.8-1.2s (freio + throttle juntos)
   - Seu padrão: provavelmente solta freio e DEPOIS aperta (separado)

5. ANÁLISE POR CURVA (RESUMIDA E COMPARATIVA):
   Formato AÇÃO-ORIENTADO para as 5-7 curvas mais importantes:
   
   CURVA X - NOME:
   ├─ Seu padrão: entra {vel}km/h, freia com {pressão}%, solta {distância}m antes ápice
   ├─ Padrão hotlap: entra ~{ideal_vel}km/h, freia ~35%, trail braking até ápice
   ├─ Problema: freia TARDE {X}m (profissional inicia em Y)
   ├─ Solução: inicia freada em {novo_ponto}m com 35% → trail braking
   ├─ Resultado esperado: entra ~{nova_vel}km/h → controle + velocidade
   └─ Ganho potencial: ~{tempo}s (só frenagem!)

CRITÉRIO DE SUCESSO:
- Compara SEMPRE com padrão profissional (hotlap)
- Números CONCRETOS (não "reduz um pouco", mas "reduz para 35%")
- Sempre explicar POR QUE (não só o QUÊ)
- Priorizar frenagem/timing acima de TUDO
- Quantificar ganho de tempo (1.5s em frenagem = ~0.3s no tempo total)
- Identificar o padrão RAIZ (não os sintomas)

Seja PRECISO e COMPARATIVO com o hotlap. Cite números SEMPRE."""

prompt_user = f"""DADOS DA VOLTA:
- Pista: {session.metadata.track_location} ({session.metadata.track_variation})
- Comprimento: {session.metadata.track_length_m:.0f}m
- Tempo total: {format_lap_time(target_lap_obj.lap_time_s)}
- Samples: {len(target_df)}

ESTATÍSTICAS GERAIS:
- Velocidade máxima: {max_speed:.1f} km/h
- Velocidade média: {avg_speed:.1f} km/h
- RPM máximo: {max_rpm}
- Acelerador médio: {avg_throttle:.1f}%
- Freio médio: {avg_brake:.1f}%
- Curvas detectadas: {len(curves)}

ANÁLISE DETALHADA POR CURVA:
"""

# Gera análise por curva (o core da análise profunda)
for i, (stat, curve) in enumerate(zip(curve_stats, curves)):
    gap_pct = (stat["speed_margin"] / stat["ideal_apex_speed"] * 100) if stat["ideal_apex_speed"] > 0 else 0
    
    # Analisa o padrão de freada desta curva
    curve_df = target_df.iloc[curve.index_start:curve.index_end]
    braking_start_idx = None
    distance_before_entry = 0
    
    for j in range(len(curve_df) - 1):
        if curve_df["brake_pct"].iloc[j] < 20 and curve_df["brake_pct"].iloc[j + 1] >= 20:
            braking_start_idx = j
            break
    
    if braking_start_idx is not None:
        braking_start_distance = curve_df["current_lap_distance"].iloc[braking_start_idx]
        distance_before_entry = curve.distance_start_m - braking_start_distance
        braking_info = f"Freio iniciado {distance_before_entry:.0f}m antes da curva"
    else:
        distance_before_entry = 0
        braking_info = "Sem freio significativo detectado nesta curva"
    
    # Estima ganho baseado em padrões
    if abs(distance_before_entry) < 20:
        gain_estimate = "0.2–0.4s"
    elif abs(stat["speed_margin"]) < 5:
        gain_estimate = "0.1–0.2s"
    else:
        gain_estimate = "0.4–0.6s"
    
    prompt_user += f"""
{stat['name']} (Curva #{stat['curve_num']}):
  FRENAGEM:
  - {braking_info}
  - Pressão média: {stat['avg_brake']:.0f}%, máx: {stat['avg_brake'] * 1.5:.0f}% (estimado)
  - Padrão: {'Abrupto (solta tudo de uma vez)' if stat['avg_brake'] > 50 else 'Progressivo (mantém durante curva)'}
  
  VELOCIDADE:
  - Entrada: {stat['speed_entry']:.0f} km/h (ideal: {stat['ideal_apex_speed']:.0f} km/h)
  - Ápice (mínima): {stat['speed_apex']:.0f} km/h
  - Saída: {stat['speed_exit']:.0f} km/h
  - Gap entrada: {(stat['ideal_apex_speed'] - stat['speed_entry']):.0f} km/h (você está {'rápido demais' if stat['speed_entry'] > stat['ideal_apex_speed'] else 'lento demais'})
  
  STEERING:
  - Máx: {stat['max_steering']:.0f}% (tipo de curva: {curve.curve_type})
  
  RECOMENDAÇÃO TRAIL BRAKING:
  - {stat['recommendation']}
  - Ganho estimado: {gain_estimate}
"""

if delta_summary:
    prompt_user += f"""
COMPARAÇÃO COM VOLTA DE REFERÊNCIA:
- Delta final: {delta_summary['final_delta_s']:+.3f}s (você está {'ganhando' if delta_summary['final_delta_s'] < 0 else 'perdendo'} tempo)
- Maior perda local: {delta_summary['max_loss_s']:+.3f}s
- Maior ganho local: {delta_summary['max_gain_s']:+.3f}s
"""

# ===========================================================================
# Funções para chamar os modelos
# ===========================================================================

def call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Chama Ollama localmente com limite de tamanho de prompt."""
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    # Limita o tamanho do prompt pra evitar timeout/OOM no Ollama
    # Mistral 7B suporta ~4096 tokens (~16000 chars). Trunca se necessário.
    MAX_CHARS = 12000
    if len(full_prompt) > MAX_CHARS:
        full_prompt = full_prompt[:MAX_CHARS] + "\n\n[Dados truncados para caber no contexto]"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False,
                "temperature": 0.7,
                "options": {
                    "num_ctx": 4096,       # contexto máximo do modelo
                    "num_predict": 1500,   # máximo de tokens na resposta
                }
            },
            timeout=180,  # 3 minutos — Mistral pode ser lento com prompt grande
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        return ("❌ **Erro: Ollama não está rodando.**\n\n"
                "Abra um terminal e execute:\n```bash\nollama serve\n```")
    except requests.exceptions.Timeout:
        return ("❌ **Timeout: Ollama demorou demais.**\n\n"
                "Tente reduzir a quantidade de curvas analisadas, "
                "ou reinicie o Ollama com `ollama serve`.")
    except Exception as e:
        return f"❌ **Erro ao chamar Ollama:** {e}"


def call_claude(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Chama Claude via API."""
    if not api_key:
        return "❌ **Chave da API Claude não fornecida.**"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text
    except anthropic.AuthenticationError:
        return "❌ **Chave da API Claude inválida.** Verifique em https://console.anthropic.com/keys"
    except anthropic.APIError as e:
        return f"❌ **Erro da API Claude:** {e}"
    except Exception as e:
        return f"❌ **Erro ao chamar Claude:** {e}"


# ===========================================================================
# UI
# ===========================================================================

st.markdown("---")

col_left, col_right = st.columns([1, 3])

with col_left:
    st.subheader("Parâmetros")
    st.metric("Volta", target_lap_num)
    st.metric("Tempo", format_lap_time(target_lap_obj.lap_time_s))
    st.metric("Vel. máx", f"{max_speed:.0f} km/h")
    st.metric("Freadas", len(braking_zones))

with col_right:
    st.subheader("Análise")

    # Verifica se tem tudo preparado
    if ai_choice == "claude" and not claude_key:
        st.error("Cole sua chave da API Claude na sidebar para continuar.")
    else:
        if st.button("🤖 Gerar análise", use_container_width=True, type="primary"):
            with st.spinner(f"Analisando com {MODELS[ai_choice]['name']}... (pode levar alguns segundos)"):
                if ai_choice == "ollama":
                    analysis = call_ollama(prompt_system, prompt_user)
                else:  # claude
                    analysis = call_claude(claude_key, prompt_system, prompt_user)

            st.markdown(analysis)

            # Cache da análise
            st.session_state.last_analysis = analysis
            st.session_state.last_lap = target_lap_num
            st.session_state.last_model = ai_choice

        elif ("last_analysis" in st.session_state and 
              st.session_state.last_lap == target_lap_num and
              st.session_state.last_model == ai_choice):
            st.markdown(st.session_state.last_analysis)

# ===========================================================================
# Info
# ===========================================================================

with st.expander("ℹ️ Como funciona"):
    st.markdown("""
    ## Escolha do modelo

    **Ollama (Grátis)**
    - Roda offline no seu PC
    - Sem limite de uso
    - Privacidade total (dados nunca saem do seu PC)
    - Qualidade: 70% do Claude
    - Velocidade: 30-60 segundos

    **Claude (Premium)**
    - Análise de qualidade profissional
    - Velocidade: 5-10 segundos
    - Custo: ~R$ 0.10–0.15 por análise
    - Chave da API não é guardada (só usada na sessão)

    ## O que você recebe

    1. **Resumo Geral:** avaliação + 2-3 pontos principais + recomendação concreta
    2. **Análise por Setor:** feedback específico pra Setor 1, 2 e 3 com impacto estimado

    ## Dica

    Comece com **Ollama** pra entender que tipo de feedback mais te ajuda.
    Depois, use **Claude** quando quiser análise muito precisa (antes de competição, etc).
    """)
