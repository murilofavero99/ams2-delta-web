"""
Service de análise de telemetria.

Integra com Ollama e Claude para análise com IA.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import anthropic
import requests

SHARED_PATH = Path(__file__).resolve().parents[3] / "shared"
if str(SHARED_PATH) not in sys.path:
    sys.path.insert(0, str(SHARED_PATH))

from ams2_delta.analysis.session import load_session, compute_delta, summarize_delta
from ams2_delta.analysis.curve_detection import detect_curves, estimate_ideal_speed
from ams2_delta.analysis.track_curves import label_curves_by_track

from ..models.schemas import AnalysisResponse, CurveInfo, DeltaSummary


class AnalysisService:
    """Gerencia análise de telemetria."""

    OLLAMA_URL = "http://localhost:11434/api/generate"
    CLAUDE_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_OPUS = "claude-opus-4-20250514"

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir

    async def analyze_lap(
        self,
        session_id: str,
        lap_number: int,
        ai_model: str,
        api_key: Optional[str] = None,
    ) -> AnalysisResponse:
        """Analisa uma volta com IA."""
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            raise ValueError(f"Sessão {session_id} não encontrada")

        session = load_session(session_dir)
        lap_df = session.lap_telemetry(lap_number)

        if lap_df.empty:
            raise ValueError(f"Volta {lap_number} sem telemetria")

        # Detecta curvas
        curves = detect_curves(lap_df, min_curve_duration_m=20.0)
        curves = label_curves_by_track(
            curves,
            session.metadata.track_location,
            session.metadata.track_variation,
        )

        # Converte pra CurveInfo
        curves_info = []
        for curve in curves:
            ideal = estimate_ideal_speed(curve)
            curves_info.append(CurveInfo(
                curve_num=curve.curve_num,
                name=curve.name,
                curve_type=curve.curve_type,
                speed_entry_kmh=curve.speed_entry_kmh,
                speed_apex_kmh=curve.speed_apex_kmh,
                speed_exit_kmh=curve.speed_exit_kmh,
                ideal_apex_speed_kmh=ideal["ideal_speed_apex_kmh"],
                speed_margin_kmh=ideal["margin_kmh"],
                recommendation=ideal["recommendation"],
                max_steering_pct=curve.max_steering_pct,
                avg_brake_pct=curve.avg_brake_pct,
                avg_throttle_pct=curve.avg_throttle_pct,
                duration_m=curve.duration_m,
            ))

        # Calcula delta se tiver volta de referência
        delta_summary = None
        valid_laps = session.valid_laps()
        if len(valid_laps) >= 2:
            fastest = session.fastest_lap()
            if fastest and fastest.lap_number != lap_number:
                ref_df = session.lap_telemetry(fastest.lap_number)
                delta_df = compute_delta(
                    lap_df, ref_df,
                    track_length_m=session.metadata.track_length_m,
                    step_m=1.0,
                )
                if not delta_df.empty:
                    summary = summarize_delta(delta_df)
                    delta_summary = DeltaSummary(
                        final_delta_s=summary["final_delta_s"],
                        max_loss_s=summary["max_loss_s"],
                        max_gain_s=summary["max_gain_s"],
                    )

        # Gera prompt
        prompt = self._build_prompt(session, lap_number, curves_info, delta_summary)

        # Chama IA
        if ai_model == "ollama":
            analysis_text = self._call_ollama(prompt)
            cost = None
            tokens = None
        elif ai_model == "gemini":
            if not api_key:
                raise ValueError("API key necessária para Gemini. Pegue grátis em aistudio.google.com/apikey")
            analysis_text = self._call_gemini(prompt, api_key)
            cost = 0.0  # gratuito no tier free
            tokens = None
        elif ai_model == "groq":
            if not api_key:
                raise ValueError("API key necessária para Groq. Pegue grátis em console.groq.com/keys")
            analysis_text = self._call_groq(prompt, api_key)
            cost = 0.0  # gratuito no tier free
            tokens = None
        elif ai_model.startswith("claude"):
            if not api_key:
                raise ValueError("API key necessária para Claude")
            model = self.CLAUDE_SONNET if "sonnet" in ai_model else self.CLAUDE_OPUS
            analysis_text, tokens = self._call_claude(prompt, api_key, model)
            cost = self._estimate_cost(tokens, model)
        else:
            raise ValueError(f"Modelo desconhecido: {ai_model}")

        return AnalysisResponse(
            analysis_text=analysis_text,
            curves=curves_info,
            delta_summary=delta_summary,
            model_used=ai_model,
            tokens_used=tokens,
            cost_estimate=cost,
        )

    def compute_delta_between_laps(self, session_id: str, lap1: int, lap2: int):
        """Calcula delta entre duas voltas."""
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            raise ValueError(f"Sessão {session_id} não encontrada")

        session = load_session(session_dir)
        df1 = session.lap_telemetry(lap1)
        df2 = session.lap_telemetry(lap2)

        if df1.empty or df2.empty:
            raise ValueError("Uma das voltas não tem telemetria")

        delta_df = compute_delta(
            df1, df2,
            track_length_m=session.metadata.track_length_m,
            step_m=1.0,
        )

        return delta_df.to_dict(orient="records")

    def _build_prompt(self, session, lap_number, curves, delta_summary) -> str:
        """Constrói prompt detalhado para análise específica da volta."""
        
        lap_info = next((l for l in session.valid_laps() if l.lap_number == lap_number), None)
        is_fastest = session.fastest_lap() and session.fastest_lap().lap_number == lap_number
        
        # Formata tempo
        lap_time_str = f"{int(lap_info.lap_time_s // 60)}:{lap_info.lap_time_s % 60:06.3f}" if lap_info else "?"
        
        # Resumo de curvas
        curves_summary = "\n".join([
            f"  • {c.name} ({c.curve_type}): "
            f"Entrada {c.speed_entry_kmh:.0f} → Ápice {c.speed_apex_kmh:.0f} → Saída {c.speed_exit_kmh:.0f} km/h "
            f"(Ideal: {c.ideal_apex_speed_kmh:.0f} | Margem: {c.speed_margin_kmh:+.1f} km/h)\n"
            f"    Freio: {c.avg_brake_pct:.0f}% | Acelerador: {c.avg_throttle_pct:.0f}%"
            for c in curves[:8]  # Limita a 8 curvas pra não ficar muito longo
        ])

        # Delta info
        delta_info = ""
        if delta_summary:
            delta_info = f"""
Delta vs Melhor Volta:
  • Final: {delta_summary.final_delta_s:+.3f}s
  • Maior perda: {delta_summary.max_loss_s:.3f}s
  • Maior ganho: {delta_summary.max_gain_s:.3f}s
"""

        prompt = f"""Você é um especialista em sim-racing do jogo Automobilista 2. 
Analise esta volta específica e forneça feedback técnico e actionable sobre a pilotagem.

═══════════════════════════════════════════════════════
DADOS DA VOLTA
═══════════════════════════════════════════════════════
Pista: {session.metadata.track_location} ({session.metadata.track_variation})
Distância: {session.metadata.track_length_m:.0f}m
Volta: #{lap_number}
Tempo: {lap_time_str}
{"🏆 MELHOR VOLTA" if is_fastest else ""}
Pista completa: {getattr(lap_info, 'completeness_pct', 100):.0f}% {"✓ Completa" if getattr(lap_info, 'completeness_pct', 100) >= 80 else "⚠ Incompleta"}{delta_info}

═══════════════════════════════════════════════════════
CURVAS DETECTADAS ({len(curves)})
═══════════════════════════════════════════════════════
{curves_summary}

═══════════════════════════════════════════════════════
INSTRUÇÕES PARA ANÁLISE
═══════════════════════════════════════════════════════
1. **Resumo Executivo**: Nota geral 1-10, ponto forte, maior fraqueza
2. **Análise de Frenagem**: 
   - Quando está frenando (muito cedo/tarde/correto?)
   - Intensidade (muita/pouca pressão?)
   - Sugestões de melhoria específicas
3. **Análise de Curvas**: 
   - Velocidades de entrada/ápice/saída
   - Comparar com ideal (se > 5 km/h abaixo do ideal, é problema)
   - Traçado (linha de ponta, mid-corner, saída)
4. **Análise de Aceleração**:
   - Timing de saída das curvas
   - Suavidade do pedal
   - Progressão de throttle
5. **Top 3 Ganhos Potenciais**: 
   - Quantos segundos cada pode ganhar
   - Como implementar (técnica específica)
6. **Padrões Gerais**: 
   - Tende a ser mais agressivo ou conservador?
   - Consistência ao longo da volta?

FORMATO: Estruture a análise com headers claros (###), use **bold** para destaque.
Seja específico com números, velocidades e recomendações técnicas.
Evite falar sobre o jogo ou a pista em geral — foque APENAS nesta volta."""

        return prompt

    def _call_ollama(self, prompt: str) -> str:
        """Chama Ollama local."""
        try:
            response = requests.post(
                self.OLLAMA_URL,
                json={
                    "model": "mistral",
                    "prompt": prompt[:12000],
                    "stream": False,
                    "options": {"num_ctx": 4096},
                },
                timeout=180,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Erro ao chamar Ollama: {e}\n\nO Ollama precisa estar rodando localmente. Esta opção não funciona na versão cloud."

    def _call_gemini(self, prompt: str, api_key: str) -> str:
        """Chama Google Gemini (gratuito até 15 req/min)."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            response = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt[:30000]}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 2048,
                    },
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except requests.HTTPError as e:
            err_msg = ""
            try:
                err_msg = e.response.json().get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)
            return f"Erro ao chamar Gemini: {err_msg}"
        except Exception as e:
            return f"Erro ao chamar Gemini: {e}"

    def _call_groq(self, prompt: str, api_key: str) -> str:
        """Chama Groq (Llama 3.1 70B - ultra rápido, gratuito)."""
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt[:25000]}],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.HTTPError as e:
            err_msg = ""
            try:
                err_msg = e.response.json().get("error", {}).get("message", str(e))
            except Exception:
                err_msg = str(e)
            return f"Erro ao chamar Groq: {err_msg}"
        except Exception as e:
            return f"Erro ao chamar Groq: {e}"

    def _call_claude(self, prompt: str, api_key: str, model: str) -> tuple[str, int]:
        """Chama Claude API."""
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        tokens = message.usage.input_tokens + message.usage.output_tokens
        return message.content[0].text, tokens

    def _estimate_cost(self, tokens: int, model: str) -> float:
        """Estima custo em reais."""
        # Preços aproximados (atualizar conforme necessário)
        if "sonnet" in model:
            return tokens * 0.000015 * 5.5  # USD to BRL
        else:  # opus
            return tokens * 0.00015 * 5.5
