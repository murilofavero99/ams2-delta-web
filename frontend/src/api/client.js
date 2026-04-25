/**
 * API client para comunicação com o backend FastAPI.
 *
 * Todas as chamadas passam pelo proxy do Vite (/api -> localhost:8000)
 */

const API_BASE = '/api';

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/** Lista todas as sessões */
export function fetchSessions() {
  return fetchJSON('/sessions/');
}

/** Detalhes de uma sessão */
export function fetchSession(sessionId) {
  return fetchJSON(`/sessions/${sessionId}`);
}

/** Telemetria de uma volta */
export function fetchLapTelemetry(sessionId, lapNumber, maxPoints = 3000) {
  return fetchJSON(
    `/sessions/${sessionId}/laps/${lapNumber}/telemetry?max_points=${maxPoints}`
  );
}

/** Delta entre duas voltas */
export function fetchDelta(sessionId, lap1, lap2) {
  return fetchJSON(`/analysis/${sessionId}/delta/${lap1}/${lap2}`);
}

/** Análise com IA */
export function analyzeWithAI(sessionId, lapNumber, aiModel = 'ollama', apiKey = null) {
  return fetchJSON(`/analysis/ai?session_id=${sessionId}`, {
    method: 'POST',
    body: JSON.stringify({
      lap_number: lapNumber,
      ai_model: aiModel,
      api_key: apiKey,
    }),
  });
}
