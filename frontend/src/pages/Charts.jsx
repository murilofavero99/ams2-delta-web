import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSessions, fetchLapTelemetry } from '../api/client';
import TelemetryCharts from '../components/TelemetryCharts';
import Loading from '../components/Loading';
import { BarChart3, ChevronDown } from 'lucide-react';

export default function Charts() {
  const [selectedSession, setSelectedSession] = useState(null);
  const [selectedLap, setSelectedLap] = useState(null);
  const [compareLap, setCompareLap] = useState(null);

  const { data: sessions } = useQuery({ queryKey: ['sessions'], queryFn: fetchSessions });

  // Auto-seleciona
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

  const { data: telemetry, isLoading } = useQuery({
    queryKey: ['telemetry', selectedSession, selectedLap],
    queryFn: () => fetchLapTelemetry(selectedSession, selectedLap, 2000),
    enabled: !!selectedSession && !!selectedLap,
  });

  const { data: compareTelemetry } = useQuery({
    queryKey: ['telemetry', selectedSession, compareLap],
    queryFn: () => fetchLapTelemetry(selectedSession, compareLap, 2000),
    enabled: !!selectedSession && !!compareLap,
  });

  return (
    <div className="min-h-screen space-y-6">
      {/* Header */}
      <header className="animate-fade-in">
        <h1 className="font-display font-extrabold text-3xl md:text-4xl text-delta-text flex items-center gap-3">
          <BarChart3 className="text-delta-accent" size={32} />
          Gráficos
        </h1>
        <p className="text-delta-muted mt-1">
          Visualize e compare a telemetria das suas voltas
        </p>
      </header>

      {/* Controles */}
      <div className="flex flex-wrap items-center gap-3 animate-slide-up">
        {/* Sessão */}
        <div className="relative">
          <select
            className="appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium text-delta-text focus:outline-none focus:border-delta-accent/50"
            value={selectedSession || ''}
            onChange={e => {
              setSelectedSession(e.target.value);
              const s = sessions.find(s => s.metadata.session_id === e.target.value);
              const f = s?.laps.find(l => l.is_fastest) || s?.laps[0];
              if (f) { setSelectedLap(f.lap_number); setCompareLap(null); }
            }}
          >
            {sessions?.filter(s => s.laps.length > 0).map(s => (
              <option key={s.metadata.session_id} value={s.metadata.session_id}>
                {s.metadata.track_location} — {s.laps.length} voltas
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
        </div>

        {/* Volta principal */}
        <div className="relative">
          <select
            className="appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium text-delta-text focus:outline-none focus:border-delta-accent/50"
            value={selectedLap || ''}
            onChange={e => setSelectedLap(Number(e.target.value))}
          >
            {currentSession?.laps.map(l => (
              <option key={l.lap_number} value={l.lap_number}>
                #{l.lap_number} — {formatTime(l.lap_time_s)}{l.is_fastest ? ' ⭐' : ''}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
        </div>

        {/* Volta de comparação (opcional) */}
        <div className="relative">
          <select
            className="appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium text-delta-muted focus:outline-none focus:border-delta-accent/50"
            value={compareLap || ''}
            onChange={e => setCompareLap(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Comparar com...</option>
            {currentSession?.laps.filter(l => l.lap_number !== selectedLap).map(l => (
              <option key={l.lap_number} value={l.lap_number}>
                #{l.lap_number} — {formatTime(l.lap_time_s)}{l.is_fastest ? ' ⭐' : ''}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
        </div>

        {compareLap && (
          <button
            onClick={() => setCompareLap(null)}
            className="text-xs text-delta-muted hover:text-delta-loss transition-colors"
          >
            Limpar comparação
          </button>
        )}
      </div>

      {/* Gráficos */}
      {isLoading && <Loading text="Carregando telemetria..." />}

      {telemetry && (
        <div className="animate-fade-in">
          <TelemetryCharts
            telemetry={telemetry}
            compareTelemetry={compareTelemetry}
            lapLabel={`Volta #${selectedLap} — ${formatTime(currentSession?.laps.find(l => l.lap_number === selectedLap)?.lap_time_s || 0)}`}
            compareLapLabel={compareLap ? `Volta #${compareLap} — ${formatTime(currentSession?.laps.find(l => l.lap_number === compareLap)?.lap_time_s || 0)}` : null}
            showCurveLabels={true}
          />
        </div>
      )}
    </div>
  );
}

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(3);
  return `${m}:${sec.padStart(6, '0')}`;
}
