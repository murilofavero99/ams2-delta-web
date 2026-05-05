import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchSessions, analyzeWithAI } from '../api/client';
import Loading from '../components/Loading';
import {
  Bot, Cpu, Cloud, ChevronDown, Play, Star,
  AlertTriangle, Target, Gauge, Zap, Shield,
} from 'lucide-react';

// ─── Modelos disponíveis ──────────────────────────────────────────────────────
const AI_MODELS = [
  {
    id: 'gemini',
    name: 'Gemini 2.0 Flash',
    desc: 'Google AI — gratuito, rápido, ótima qualidade',
    icon: Cloud,
    speed: '3-8s',
    quality: 92,
    cost: 'R$ 0',
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
    border: 'border-blue-400/30',
    needsKey: true,
    keyName: 'Gemini',
    keyPlaceholder: 'AIza...',
    keyUrl: 'aistudio.google.com/apikey',
  },
  {
    id: 'groq',
    name: 'Groq (Llama 3.3 70B)',
    desc: 'Groq — Llama 70B, ultra rápido, gratuito',
    icon: Zap,
    speed: '1-3s',
    quality: 90,
    cost: 'R$ 0',
    color: 'text-orange-400',
    bg: 'bg-orange-400/10',
    border: 'border-orange-400/30',
    needsKey: true,
    keyName: 'Groq',
    keyPlaceholder: 'gsk_...',
    keyUrl: 'console.groq.com/keys',
  },
  {
    id: 'ollama',
    name: 'Ollama (Local)',
    desc: 'Mistral 7B — só funciona localmente',
    icon: Cpu,
    speed: '30-60s',
    quality: 70,
    cost: 'R$ 0',
    color: 'text-delta-accent',
    bg: 'bg-delta-accent/10',
    border: 'border-delta-accent/30',
    localOnly: true,
  },
  {
    id: 'claude-sonnet',
    name: 'Claude Sonnet',
    desc: 'Anthropic API — pago, excelente qualidade',
    icon: Cloud,
    speed: '5-10s',
    quality: 95,
    cost: '~R$ 0.10',
    color: 'text-purple-400',
    bg: 'bg-purple-400/10',
    border: 'border-purple-400/30',
    needsKey: true,
    keyName: 'Anthropic',
    keyPlaceholder: 'sk-ant-...',
    keyUrl: 'console.anthropic.com',
  },
  {
    id: 'claude-opus',
    name: 'Claude Opus',
    desc: 'Anthropic API — máxima qualidade, mais lento',
    icon: Cloud,
    speed: '10-20s',
    quality: 100,
    cost: '~R$ 0.75',
    color: 'text-amber-400',
    bg: 'bg-amber-400/10',
    border: 'border-amber-400/30',
    needsKey: true,
    keyName: 'Anthropic',
    keyPlaceholder: 'sk-ant-...',
    keyUrl: 'console.anthropic.com',
  },
];

export default function AIAnalysis() {
  const [selectedSession, setSelectedSession] = useState(null);
  const [selectedLap, setSelectedLap] = useState(null);
  const [selectedModel, setSelectedModel] = useState('gemini');
  const [apiKey, setApiKey] = useState('');

  const { data: sessions } = useQuery({ queryKey: ['sessions'], queryFn: fetchSessions });

  // Auto-seleciona primeira sessão com voltas
  useEffect(() => {
    if (sessions?.length && !selectedSession) {
      const s = sessions.find(s => s.laps.length > 0);
      if (s) {
        setSelectedSession(s.metadata.session_id);
        const fastest = s.laps.find(l => l.is_fastest) || s.laps[0];
        if (fastest) setSelectedLap(fastest.lap_number);
      }
    }
  }, [sessions]);

  const currentSession = sessions?.find(s => s.metadata.session_id === selectedSession);
  const currentLap = currentSession?.laps.find(l => l.lap_number === selectedLap);
  const modelInfo = AI_MODELS.find(m => m.id === selectedModel);

  // Mutation pra chamar IA
  const mutation = useMutation({
    mutationFn: () => analyzeWithAI(selectedSession, selectedLap, selectedModel, apiKey || null),
  });

  const canAnalyze = selectedSession && selectedLap &&
    (modelInfo?.localOnly || (modelInfo?.needsKey && apiKey.length > 10) || (!modelInfo?.needsKey && !modelInfo?.localOnly));

  return (
    <div className="min-h-screen space-y-6">
      {/* Header */}
      <header className="animate-fade-in">
        <h1 className="font-display font-extrabold text-3xl md:text-4xl text-delta-text flex items-center gap-3">
          <Bot className="text-delta-accent" size={32} />
          Análise com IA
        </h1>
        <p className="text-delta-muted mt-1">
          Feedback automático sobre sua pilotagem — frenagem, traçado, aceleração
        </p>
      </header>

      {/* Configuração */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-slide-up">

        {/* Coluna 1: Sessão e Volta */}
        <div className="glass-card p-5 space-y-4">
          <h2 className="text-xs uppercase tracking-widest text-delta-muted font-medium">
            Sessão
          </h2>

          {/* Seletor de sessão */}
          <div className="relative">
            <select
              className="w-full appearance-none bg-delta-surface border border-delta-border rounded-xl px-4 py-3 text-sm font-medium text-delta-text focus:outline-none focus:border-delta-accent/50"
              value={selectedSession || ''}
              onChange={e => {
                setSelectedSession(e.target.value);
                const s = sessions.find(s => s.metadata.session_id === e.target.value);
                const f = s?.laps.find(l => l.is_fastest) || s?.laps[0];
                if (f) setSelectedLap(f.lap_number);
              }}
            >
              <option value="">Selecione uma sessão</option>
              {sessions?.filter(s => s.laps.length > 0).map(s => (
                <option key={s.metadata.session_id} value={s.metadata.session_id}>
                  {s.metadata.track_location} — {s.laps.length} voltas
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
          </div>

          {/* Seletor de volta */}
          {currentSession && (
            <div className="space-y-2">
              <h3 className="text-xs text-delta-muted font-medium">Volta</h3>
              {currentSession.laps.map(lap => (
                <button
                  key={lap.lap_number}
                  onClick={() => setSelectedLap(lap.lap_number)}
                  className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all text-sm ${
                    selectedLap === lap.lap_number
                      ? 'bg-delta-accent/10 border-delta-accent/40 text-delta-accent'
                      : 'bg-delta-surface/50 border-delta-border hover:border-delta-accent/20 text-delta-text'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-delta-muted">#{lap.lap_number}</span>
                    <span className="font-mono font-semibold">{formatTime(lap.lap_time_s)}</span>
                    {lap.is_fastest && <Star size={14} className="text-delta-warn fill-delta-warn" />}
                  </div>
                  <span className="badge-complete text-[10px]">{lap.completeness_pct.toFixed(0)}%</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Coluna 2: Modelo de IA */}
        <div className="glass-card p-5 space-y-4">
          <h2 className="text-xs uppercase tracking-widest text-delta-muted font-medium">
            Modelo de IA
          </h2>

          <div className="space-y-3">
            {AI_MODELS.map(model => {
              const Icon = model.icon;
              const active = selectedModel === model.id;
              return (
                <button
                  key={model.id}
                  onClick={() => setSelectedModel(model.id)}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    active
                      ? `${model.bg} ${model.border}`
                      : 'bg-delta-surface/30 border-delta-border hover:border-delta-accent/20'
                  }`}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <Icon size={18} className={active ? model.color : 'text-delta-muted'} />
                    <span className={`font-medium text-sm ${active ? model.color : 'text-delta-text'}`}>
                      {model.name}
                    </span>
                  </div>
                  <p className="text-xs text-delta-muted mb-2">{model.desc}</p>
                  <div className="flex items-center gap-4 text-[10px] font-mono text-delta-muted">
                    <span>⏱️ {model.speed}</span>
                    <span>💰 {model.cost}</span>
                    <span>
                      ⭐ {model.quality}%
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Chave da API (pra modelos que precisam) */}
          {modelInfo?.needsKey && (
            <div className="space-y-2 animate-fade-in">
              <label className="text-xs text-delta-muted font-medium">
                Chave da API {modelInfo.keyName}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={modelInfo.keyPlaceholder}
                className="w-full bg-delta-surface border border-delta-border rounded-xl px-4 py-2.5 text-sm font-mono text-delta-text placeholder:text-delta-muted/40 focus:outline-none focus:border-delta-accent/50"
              />
              <p className="text-[10px] text-delta-muted">
                Obtém em <a href={`https://${modelInfo.keyUrl}`} target="_blank" rel="noopener" className="text-delta-accent hover:underline">{modelInfo.keyUrl}</a> — não é guardada
              </p>
            </div>
          )}

          {/* Aviso pro Ollama */}
          {modelInfo?.localOnly && (
            <div className="p-3 rounded-xl bg-delta-warn/10 border border-delta-warn/20 text-xs text-delta-warn animate-fade-in">
              ⚠️ Ollama só funciona quando rodando localmente (<code className="font-mono text-[10px] bg-delta-bg/50 px-1.5 py-0.5 rounded">ollama serve</code>).
              Na versão cloud, escolha Gemini ou Groq (gratuitos).
            </div>
          )}
        </div>

        {/* Coluna 3: Botão + Info */}
        <div className="glass-card p-5 space-y-4 flex flex-col">
          <h2 className="text-xs uppercase tracking-widest text-delta-muted font-medium">
            Análise
          </h2>

          {/* Resumo da seleção */}
          {currentLap && (
            <div className="space-y-3 flex-1">
              <div className="grid grid-cols-2 gap-3">
                <InfoBox icon={Target} label="Pista" value={currentSession?.metadata.track_location || '—'} />
                <InfoBox icon={Gauge} label="Tempo" value={formatTime(currentLap.lap_time_s)} />
                <InfoBox icon={Cpu} label="Modelo" value={modelInfo?.name || '—'} />
                <InfoBox icon={Shield} label="Custo" value={modelInfo?.cost || '—'} />
              </div>

              {currentLap.is_fastest && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-delta-warn/10 border border-delta-warn/20 text-xs text-delta-warn">
                  <Star size={14} className="fill-delta-warn" />
                  Analisando sua melhor volta
                </div>
              )}
            </div>
          )}

          {/* Botão */}
          <button
            onClick={() => mutation.mutate()}
            disabled={!canAnalyze || mutation.isPending}
            className={`w-full flex items-center justify-center gap-2 px-6 py-4 rounded-xl font-display font-semibold text-sm transition-all ${
              canAnalyze && !mutation.isPending
                ? 'bg-delta-accent text-delta-bg hover:brightness-110 active:scale-95'
                : 'bg-delta-border text-delta-muted cursor-not-allowed'
            }`}
          >
            {mutation.isPending ? (
              <>
                <div className="w-4 h-4 border-2 border-delta-bg/30 border-t-delta-bg rounded-full animate-spin" />
                Analisando...
              </>
            ) : (
              <>
                <Play size={16} />
                Gerar Análise
              </>
            )}
          </button>

          {!canAnalyze && modelInfo?.needsKey && !apiKey && (
            <p className="text-xs text-delta-loss text-center">
              Cole a chave da API acima
            </p>
          )}
        </div>
      </div>

      {/* ── Resultado da análise ── */}
      {mutation.isPending && (
        <div className="glass-card p-8 animate-fade-in">
          <Loading text={`Analisando com ${modelInfo?.name}... pode levar ${modelInfo?.speed}`} />
        </div>
      )}

      {mutation.isError && (
        <div className="glass-card p-6 border-delta-loss/30 animate-slide-up">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-delta-loss mt-0.5" size={20} />
            <div>
              <p className="text-delta-loss font-medium">Erro na análise</p>
              <p className="text-sm text-delta-muted mt-1">{mutation.error?.message}</p>
              {selectedModel === 'ollama' && (
                <p className="text-xs text-delta-muted mt-3">
                  Verifique se o Ollama está rodando: <code className="text-delta-accent">ollama serve</code>
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {mutation.isSuccess && (
        <div className="space-y-6 animate-slide-up">
          {/* Curvas detectadas */}
          {mutation.data.curves?.length > 0 && (
            <div className="glass-card p-6">
              <h2 className="font-display font-semibold text-lg text-delta-text mb-4 flex items-center gap-2">
                <Target size={18} className="text-delta-accent" />
                Curvas Detectadas ({mutation.data.curves.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {mutation.data.curves.map((curve, i) => (
                  <CurveCard key={i} curve={curve} />
                ))}
              </div>
            </div>
          )}

          {/* Texto da análise */}
          <div className="glass-card p-6">
            <h2 className="font-display font-semibold text-lg text-delta-text mb-4 flex items-center gap-2">
              <Bot size={18} className="text-delta-accent" />
              Análise Completa
            </h2>

            {/* Meta info */}
            <div className="flex items-center gap-4 mb-6 text-xs font-mono text-delta-muted">
              <span>Modelo: {mutation.data.model_used}</span>
              {mutation.data.tokens_used && <span>Tokens: {mutation.data.tokens_used}</span>}
              {mutation.data.cost_estimate && <span>Custo: R$ {mutation.data.cost_estimate.toFixed(2)}</span>}
            </div>

            {/* Texto renderizado */}
            <div className="prose prose-invert prose-sm max-w-none">
              <AnalysisText text={mutation.data.analysis_text} />
            </div>
          </div>

          {/* Delta summary */}
          {mutation.data.delta_summary && (
            <div className="glass-card p-6">
              <h2 className="font-display font-semibold text-lg text-delta-text mb-4 flex items-center gap-2">
                <Zap size={18} className="text-delta-gain" />
                Delta vs Melhor Volta
              </h2>
              <div className="grid grid-cols-3 gap-4">
                <DeltaMetric
                  label="Delta Final"
                  value={mutation.data.delta_summary.final_delta_s}
                />
                <DeltaMetric
                  label="Maior Perda"
                  value={mutation.data.delta_summary.max_loss_s}
                />
                <DeltaMetric
                  label="Maior Ganho"
                  value={mutation.data.delta_summary.max_gain_s}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Subcomponentes ───────────────────────────────────────────────────────────

function InfoBox({ icon: Icon, label, value }) {
  return (
    <div className="p-3 rounded-xl bg-delta-surface/50 border border-delta-border/50">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} className="text-delta-muted" />
        <span className="text-[10px] uppercase tracking-widest text-delta-muted">{label}</span>
      </div>
      <p className="text-sm font-medium font-mono text-delta-text">{value}</p>
    </div>
  );
}

function CurveCard({ curve }) {
  const marginColor = curve.speed_margin_kmh > 10
    ? 'text-delta-loss'
    : curve.speed_margin_kmh > 0
      ? 'text-delta-warn'
      : 'text-delta-gain';

  return (
    <div className="p-4 rounded-xl bg-delta-surface/50 border border-delta-border/50 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-delta-text">{curve.name}</h3>
        <span className="text-[10px] font-mono text-delta-muted px-2 py-0.5 rounded-full bg-delta-border/50">
          {curve.curve_type}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] text-delta-muted">Entrada</p>
          <p className="text-sm font-mono font-medium text-delta-text">{curve.speed_entry_kmh.toFixed(0)}</p>
        </div>
        <div>
          <p className="text-[10px] text-delta-muted">Ápice</p>
          <p className="text-sm font-mono font-medium text-delta-accent">{curve.speed_apex_kmh.toFixed(0)}</p>
        </div>
        <div>
          <p className="text-[10px] text-delta-muted">Saída</p>
          <p className="text-sm font-mono font-medium text-delta-text">{curve.speed_exit_kmh.toFixed(0)}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs">
        <span className="text-delta-muted">
          Ideal: {curve.ideal_apex_speed_kmh.toFixed(0)} km/h
        </span>
        <span className={`font-mono font-medium ${marginColor}`}>
          {curve.speed_margin_kmh > 0 ? '+' : ''}{curve.speed_margin_kmh.toFixed(0)} km/h
        </span>
      </div>

      <p className="text-[10px] text-delta-muted leading-relaxed">
        {curve.recommendation}
      </p>
    </div>
  );
}

function DeltaMetric({ label, value }) {
  const color = value < 0 ? 'text-delta-gain' : value > 0 ? 'text-delta-loss' : 'text-delta-text';
  const prefix = value > 0 ? '+' : '';
  return (
    <div className="text-center p-4 rounded-xl bg-delta-surface/50">
      <p className="text-xs text-delta-muted mb-1">{label}</p>
      <p className={`font-mono font-bold text-xl ${color}`}>
        {prefix}{value.toFixed(3)}s
      </p>
    </div>
  );
}

function AnalysisText({ text }) {
  if (!text) return null;

  // Converte markdown básico em HTML
  const lines = text.split('\n');

  return (
    <div className="space-y-3 text-delta-text/90 leading-relaxed">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-2" />;

        // Headers
        if (trimmed.startsWith('###')) return <h4 key={i} className="font-display font-bold text-base text-delta-text mt-4">{trimmed.replace(/^###\s*/, '')}</h4>;
        if (trimmed.startsWith('##')) return <h3 key={i} className="font-display font-bold text-lg text-delta-text mt-5">{trimmed.replace(/^##\s*/, '')}</h3>;
        if (trimmed.startsWith('#')) return <h2 key={i} className="font-display font-bold text-xl text-delta-accent mt-6">{trimmed.replace(/^#\s*/, '')}</h2>;

        // Bullet points
        if (trimmed.startsWith('- ') || trimmed.startsWith('* '))
          return <p key={i} className="text-sm pl-4 border-l-2 border-delta-border">{trimmed.replace(/^[-*]\s*/, '')}</p>;

        // Numbered lists
        if (/^\d+[\.\)]/.test(trimmed))
          return <p key={i} className="text-sm pl-4 border-l-2 border-delta-accent/30">{trimmed}</p>;

        // Bold sections (tipo "RESUMO:", "FRENAGEM:", etc)
        if (trimmed.match(/^[A-Z\u00C0-\u00DC]{3,}/) || trimmed.endsWith(':'))
          return <h4 key={i} className="font-display font-bold text-sm text-delta-accent mt-4 uppercase tracking-wider">{trimmed}</h4>;

        // Parágrafo normal
        return <p key={i} className="text-sm">{trimmed}</p>;
      })}
    </div>
  );
}

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(3);
  return `${m}:${sec.padStart(6, '0')}`;
}
