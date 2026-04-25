import { Star, AlertTriangle } from 'lucide-react';

/**
 * Seletor de volta com visual de lista.
 */
export default function LapSelector({ laps, selectedLap, onSelect }) {
  return (
    <div className="space-y-2">
      {laps.map((lap) => (
        <button
          key={lap.lap_number}
          onClick={() => onSelect(lap.lap_number)}
          className={`w-full flex items-center justify-between p-4 rounded-xl border transition-all ${
            selectedLap === lap.lap_number
              ? 'bg-delta-accent/10 border-delta-accent/40 text-delta-accent'
              : 'bg-delta-card/50 border-delta-border hover:border-delta-accent/20'
          }`}
        >
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-delta-muted">
              #{lap.lap_number}
            </span>
            <span className="font-mono font-semibold text-lg">
              {formatTime(lap.lap_time_s)}
            </span>
            {lap.is_fastest && (
              <Star size={16} className="text-delta-warn fill-delta-warn" />
            )}
          </div>

          <div className="flex items-center gap-2">
            {lap.num_resets > 0 && (
              <span className="badge-incomplete">
                <AlertTriangle size={10} className="mr-1" />
                {lap.num_resets} reset{lap.num_resets > 1 ? 's' : ''}
              </span>
            )}
            <span className="badge-complete">
              {lap.completeness_pct.toFixed(0)}%
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(3);
  return `${mins}:${secs.padStart(6, '0')}`;
}
