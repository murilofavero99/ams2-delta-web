import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

/**
 * Card de métrica com valor grande, label, e trend opcional.
 *
 * Props:
 *   label: "Vel. Máx"
 *   value: "257.9"
 *   unit: "km/h"
 *   trend: "+3.2" (opcional, mostra seta verde/vermelha)
 *   accent: boolean (destaque com borda colorida)
 *   delay: número (delay de animação em ms)
 */
export default function MetricCard({ label, value, unit, trend, accent = false, delay = 0 }) {
  const trendValue = trend ? parseFloat(trend) : null;
  const trendColor = trendValue > 0 ? 'text-delta-gain' : trendValue < 0 ? 'text-delta-loss' : 'text-delta-muted';
  const TrendIcon = trendValue > 0 ? TrendingUp : trendValue < 0 ? TrendingDown : Minus;

  return (
    <div
      className={`glass-card p-5 animate-slide-up ${accent ? 'border-delta-accent/40 accent-glow' : ''}`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <p className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-2">
        {label}
      </p>
      <div className="flex items-end justify-between">
        <div className="flex items-baseline gap-1.5">
          <span className="metric-value text-3xl text-delta-text">
            {value}
          </span>
          {unit && (
            <span className="text-sm text-delta-muted font-mono">{unit}</span>
          )}
        </div>
        {trendValue !== null && (
          <div className={`flex items-center gap-1 text-sm font-mono ${trendColor}`}>
            <TrendIcon size={14} />
            <span>{trend}</span>
          </div>
        )}
      </div>
    </div>
  );
}
