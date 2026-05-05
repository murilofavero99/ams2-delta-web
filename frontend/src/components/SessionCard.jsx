import { useNavigate } from 'react-router-dom';
import { MapPin, Clock, Flag, Zap, ChevronRight, Car } from 'lucide-react';

/**
 * Card de sessão para a lista principal.
 */
export default function SessionCard({ session, delay = 0 }) {
  const navigate = useNavigate();
  const { metadata, laps } = session;

  const fastestLap = laps.find(l => l.is_fastest);
  const fastestTime = fastestLap ? formatTime(fastestLap.lap_time_s) : '—';

  return (
    <button
      onClick={() => navigate(`/session/${metadata.session_id}`)}
      className="glass-card p-6 w-full text-left group animate-slide-up cursor-pointer"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="font-display font-bold text-xl text-delta-text group-hover:text-delta-accent transition-colors">
            {metadata.track_location}
          </h3>
          <p className="text-sm text-delta-muted mt-0.5">
            {metadata.track_variation}
          </p>
          {metadata.car_name && (
            <p className="text-xs text-delta-accent mt-1.5 flex items-center gap-1.5">
              <Car size={12} />
              <span className="font-mono">{metadata.car_name}</span>
              {metadata.car_class_name && (
                <span className="text-delta-muted">· {metadata.car_class_name}</span>
              )}
            </p>
          )}
        </div>
        <ChevronRight
          size={20}
          className="text-delta-muted group-hover:text-delta-accent group-hover:translate-x-1 transition-all"
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-delta-accent" />
          <div>
            <p className="text-xs text-delta-muted">Pista</p>
            <p className="text-sm font-mono font-medium">{metadata.track_length_m.toFixed(0)}m</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Flag size={14} className="text-delta-accent" />
          <div>
            <p className="text-xs text-delta-muted">Voltas</p>
            <p className="text-sm font-mono font-medium">{laps.length}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Zap size={14} className="text-delta-gain" />
          <div>
            <p className="text-xs text-delta-muted">Melhor</p>
            <p className="text-sm font-mono font-medium text-delta-gain">{fastestTime}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Clock size={14} className="text-delta-muted" />
          <div>
            <p className="text-xs text-delta-muted">Data</p>
            <p className="text-sm font-mono font-medium">{formatDate(metadata.started_at)}</p>
          </div>
        </div>
      </div>
    </button>
  );
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(3);
  return `${mins}:${secs.padStart(6, '0')}`;
}

function formatDate(dateStr) {
  // formato: "20260424_123249"
  if (!dateStr || dateStr.length < 8) return dateStr;
  const y = dateStr.slice(0, 4);
  const m = dateStr.slice(4, 6);
  const d = dateStr.slice(6, 8);
  return `${d}/${m}/${y}`;
}
