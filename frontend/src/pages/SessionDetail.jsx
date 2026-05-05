import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowLeft, MapPin, Ruler, Flag, Timer, Gauge, Zap, Car } from 'lucide-react';
import { fetchSession, fetchLapTelemetry } from '../api/client';
import MetricCard from '../components/MetricCard';
import LapSelector from '../components/LapSelector';
import Loading from '../components/Loading';
import TelemetryCharts from '../components/TelemetryCharts';

export default function SessionDetail() {
  const { sessionId } = useParams();
  const [selectedLap, setSelectedLap] = useState(null);

  const { data: session, isLoading } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => fetchSession(sessionId),
  });

  const { data: telemetry, isLoading: telLoading } = useQuery({
    queryKey: ['telemetry', sessionId, selectedLap],
    queryFn: () => fetchLapTelemetry(sessionId, selectedLap, 2000),
    enabled: !!selectedLap,
  });

  // Auto-seleciona a volta mais rápida
  if (session && !selectedLap) {
    const fastest = session.laps.find(l => l.is_fastest);
    if (fastest) setSelectedLap(fastest.lap_number);
    else if (session.laps.length > 0) setSelectedLap(session.laps[0].lap_number);
  }

  if (isLoading) return <Loading text="Carregando sessão..." />;
  if (!session) return <p className="text-delta-loss">Sessão não encontrada</p>;

  const { metadata, laps } = session;
  const currentLap = laps.find(l => l.lap_number === selectedLap);

  // Calcula métricas da telemetria
  const maxSpeed = telemetry ? Math.max(...telemetry.map(t => t.speed_kmh)) : 0;
  const avgSpeed = telemetry ? (telemetry.reduce((sum, t) => sum + t.speed_kmh, 0) / telemetry.length) : 0;
  const maxRPM = telemetry ? Math.max(...telemetry.map(t => t.rpm)) : 0;

  return (
    <div className="min-h-screen">
      {/* Back + Header */}
      <div className="mb-8 animate-fade-in">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-delta-muted hover:text-delta-accent transition-colors mb-4"
        >
          <ArrowLeft size={16} />
          Voltar
        </Link>

        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="font-display font-extrabold text-3xl md:text-4xl text-delta-text">
              {metadata.track_location}
            </h1>
            <p className="text-delta-muted mt-1">{metadata.track_variation}</p>
            {metadata.car_name && (
              <p className="mt-2 inline-flex items-center gap-1.5 text-sm text-delta-accent">
                <Car size={14} />
                <span className="font-mono">{metadata.car_name}</span>
                {metadata.car_class_name && (
                  <span className="text-delta-muted">· {metadata.car_class_name}</span>
                )}
              </p>
            )}
          </div>

          <div className="flex items-center gap-6 text-sm text-delta-muted">
            <span className="flex items-center gap-1.5">
              <Ruler size={14} className="text-delta-accent" />
              {metadata.track_length_m.toFixed(0)}m
            </span>
            <span className="flex items-center gap-1.5">
              <Flag size={14} className="text-delta-accent" />
              {laps.length} voltas
            </span>
          </div>
        </div>
      </div>

      {/* Métricas */}
      {currentLap && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <MetricCard
            label="Tempo"
            value={formatTime(currentLap.lap_time_s)}
            accent={currentLap.is_fastest}
            delay={0}
          />
          <MetricCard
            label="Vel. Máx"
            value={maxSpeed.toFixed(1)}
            unit="km/h"
            delay={80}
          />
          <MetricCard
            label="Vel. Média"
            value={avgSpeed.toFixed(1)}
            unit="km/h"
            delay={160}
          />
          <MetricCard
            label="RPM Máx"
            value={maxRPM.toLocaleString()}
            delay={240}
          />
        </div>
      )}

      {/* Layout: Voltas + Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar: lista de voltas */}
        <div className="lg:col-span-1">
          <h2 className="font-display font-semibold text-sm uppercase tracking-widest text-delta-muted mb-4">
            Voltas
          </h2>
          <LapSelector
            laps={laps}
            selectedLap={selectedLap}
            onSelect={setSelectedLap}
          />
        </div>

        {/* Main: gráficos */}
        <div className="lg:col-span-3">
          <h2 className="font-display font-semibold text-sm uppercase tracking-widest text-delta-muted mb-4">
            Telemetria
          </h2>

          {telLoading && <Loading text="Carregando telemetria..." />}

          {telemetry && telemetry.length > 0 && (
            <TelemetryCharts telemetry={telemetry} />
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(3);
  return `${mins}:${secs.padStart(6, '0')}`;
}
