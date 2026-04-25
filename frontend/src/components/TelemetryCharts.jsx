import { useState, useEffect } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  AreaChart,
  Area,
} from 'recharts';
import { X, Maximize2 } from 'lucide-react';

/** Formata distância */
function formatDist(meters) {
  if (meters === 0) return '0';
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)}`;
  return `${meters}`;
}

const xAxisConfig = {
  dataKey: 'dist',
  tick: { fontSize: 11, fill: '#6b6b8a', fontFamily: 'JetBrains Mono, monospace' },
  tickFormatter: formatDist,
  type: 'number',
  domain: ['dataMin', 'dataMax'],
  tickCount: 10,
  axisLine: { stroke: '#2a2a3a' },
  tickLine: { stroke: '#2a2a3a' },
  label: { value: 'km', position: 'insideBottomRight', offset: -5, fontSize: 10, fill: '#6b6b8a' },
};

const yAxisConfig = {
  tick: { fontSize: 11, fill: '#6b6b8a', fontFamily: 'JetBrains Mono, monospace' },
  width: 50,
  axisLine: false,
  tickLine: false,
};

const chartMargin = { top: 5, right: 10, left: 0, bottom: 5 };

const COLORS = {
  speed: '#00d4ff', throttle: '#00ff88', brake: '#ff4466', steering: '#ffaa00',
  speed2: '#7eaaff', throttle2: '#88ffbb', brake2: '#ff8899', steering2: '#ffcc66',
};

function downsample(telemetry, maxPoints = 500) {
  const step = Math.max(1, Math.floor(telemetry.length / maxPoints));
  return telemetry.filter((_, i) => i % step === 0).map(t => ({
    dist: Math.round(t.current_lap_distance),
    speed: Math.round(t.speed_kmh * 10) / 10,
    throttle: Math.round(t.throttle_pct * 10) / 10,
    brake: Math.round(t.brake_pct * 10) / 10,
    steering: Math.round(t.steering_pct * 10) / 10,
    gear: t.gear,
  }));
}

function mergeByDistance(data1, data2) {
  const map = new Map();
  const snap = (d) => Math.round(d / 5) * 5;
  for (const p of data1) {
    const d = snap(p.dist);
    map.set(d, { dist: d, speed: p.speed, throttle: p.throttle, brake: p.brake, steering: p.steering, gear: p.gear });
  }
  for (const p of data2) {
    const d = snap(p.dist);
    const existing = map.get(d) || { dist: d };
    existing.speed2 = p.speed; existing.throttle2 = p.throttle;
    existing.brake2 = p.brake; existing.steering2 = p.steering;
    map.set(d, existing);
  }
  return Array.from(map.values()).sort((a, b) => a.dist - b.dist);
}

function OverlayTooltip({ active, payload, label, lapLabel, compareLapLabel }) {
  if (!active || !payload?.length) return null;
  const main = {}, compare = {};
  for (const p of payload) {
    if (p.dataKey.endsWith('2')) compare[p.dataKey.replace('2', '')] = p;
    else main[p.dataKey] = p;
  }
  return (
    <div className="bg-delta-card/95 backdrop-blur-sm border border-delta-border rounded-xl px-4 py-3 shadow-2xl">
      <p className="text-xs text-delta-muted font-mono mb-2">{formatDist(label)} km</p>
      {Object.keys(main).length > 0 && (
        <div className="mb-2">
          <p className="text-[10px] text-delta-accent font-medium mb-1">{lapLabel || 'Principal'}</p>
          {Object.values(main).map((p, i) => (
            <p key={i} className="text-xs font-mono" style={{ color: p.color }}>
              {fmtName(p.dataKey)}: {p.value?.toFixed(1)}{fmtUnit(p.dataKey)}
            </p>
          ))}
        </div>
      )}
      {Object.keys(compare).length > 0 && (
        <div className="border-t border-delta-border/50 pt-2">
          <p className="text-[10px] text-delta-muted font-medium mb-1">{compareLapLabel || 'Comparação'}</p>
          {Object.values(compare).map((p, i) => (
            <p key={i} className="text-xs font-mono" style={{ color: p.color }}>
              {fmtName(p.dataKey.replace('2', ''))}: {p.value?.toFixed(1)}{fmtUnit(p.dataKey)}
            </p>
          ))}
          {main.speed && compare.speed && (
            <p className={`text-xs font-mono font-bold mt-1 ${main.speed.value > compare.speed.value ? 'text-delta-gain' : 'text-delta-loss'}`}>
              Δ vel: {(main.speed.value - compare.speed.value).toFixed(1)} km/h
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function fmtName(k) { return { speed: 'Vel', throttle: 'Acel', brake: 'Freio', steering: 'Volante' }[k] || k; }
function fmtUnit(k) { return k.includes('speed') ? ' km/h' : '%'; }

/**
 * Gráficos de telemetria com sobreposição.
 *
 * Props:
 *   telemetry         - dados da volta principal (obrigatório)
 *   compareTelemetry  - dados da volta de comparação (opcional)
 *   lapLabel          - ex: "Volta #4 — 1:37.512"
 *   compareLapLabel   - ex: "Volta #1 — 1:38.087"
 *   curves            - array de curvas detectadas (opcional)
 *   showCurveLabels   - bool: mostrar números de curva no eixo X (default: true)
 */
export default function TelemetryCharts({ telemetry, compareTelemetry = null, lapLabel = null, compareLapLabel = null, curves = null, showCurveLabels = true }) {
  const [expandedChart, setExpandedChart] = useState(null);

  // Fechar modal com ESC
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') setExpandedChart(null);
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, []);

  const data1 = downsample(telemetry);
  const hasCompare = compareTelemetry && compareTelemetry.length > 0;
  const data = hasCompare ? mergeByDistance(data1, downsample(compareTelemetry)) : data1;
  const tooltipProps = { content: <OverlayTooltip lapLabel={lapLabel} compareLapLabel={compareLapLabel} /> };

  // Customiza eixo X se tiver curvas
  let xAxisConfigToUse = xAxisConfig;
  if (showCurveLabels && curves && curves.length > 0) {
    xAxisConfigToUse = {
      ...xAxisConfig,
      tickFormatter: (value) => {
        // Procura curva próxima a este ponto
        for (let i = 0; i < Math.min(curves.length, 8); i++) {
          const c = curves[i];
          const curvePos = c.speed_entry_kmh * 10; // posição aproximada
          if (Math.abs(curvePos - value) < 100) {
            return `#${i + 1}`;
          }
        }
        return formatDist(value);
      },
    };
  }

  return (
    <>
      <div className="space-y-6 animate-fade-in">
        {hasCompare && (
          <div className="flex items-center gap-6 px-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-0.5 rounded-full" style={{ backgroundColor: COLORS.speed }} />
              <span className="text-xs font-mono text-delta-text">{lapLabel || 'Principal'}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-6 h-0.5 rounded-full border border-dashed" style={{ borderColor: COLORS.speed2 }} />
              <span className="text-xs font-mono text-delta-muted">{compareLapLabel || 'Comparação'}</span>
            </div>
          </div>
        )}

        <ChartCard title="Velocidade" unit="km/h" onExpand={() => setExpandedChart('speed')}>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis {...xAxisConfigToUse} />
              <YAxis {...yAxisConfig} />
              <Tooltip {...tooltipProps} />
              <Line type="monotone" dataKey="speed" name="speed" stroke={COLORS.speed} strokeWidth={2} dot={false} connectNulls />
              {hasCompare && <Line type="monotone" dataKey="speed2" name="speed2" stroke={COLORS.speed2} strokeWidth={1.5} strokeDasharray="6 3" strokeOpacity={0.7} dot={false} connectNulls />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Acelerador" subtitle={hasCompare ? 'Sólido = principal · Tracejado = comparação' : null} unit="%" onExpand={() => setExpandedChart('throttle')}>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis {...xAxisConfigToUse} />
              <YAxis {...yAxisConfig} domain={[0, 100]} />
              <Tooltip {...tooltipProps} />
              <Line type="monotone" dataKey="throttle" name="throttle" stroke={COLORS.throttle} strokeWidth={1.5} dot={false} connectNulls />
              {hasCompare && <Line type="monotone" dataKey="throttle2" name="throttle2" stroke={COLORS.throttle2} strokeWidth={1.5} strokeDasharray="6 3" strokeOpacity={0.6} dot={false} connectNulls />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Freio" subtitle={hasCompare ? 'Compare quando e quanto cada volta freia' : null} unit="%" onExpand={() => setExpandedChart('brake')}>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={data} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis {...xAxisConfigToUse} />
              <YAxis {...yAxisConfig} domain={[0, 100]} />
              <Tooltip {...tooltipProps} />
              <defs>
                <linearGradient id="brakeGrad1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={COLORS.brake} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={COLORS.brake} stopOpacity={0} />
                </linearGradient>
                {hasCompare && (
                  <linearGradient id="brakeGrad2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.brake2} stopOpacity={0.15} />
                    <stop offset="100%" stopColor={COLORS.brake2} stopOpacity={0} />
                  </linearGradient>
                )}
              </defs>
              <Area type="monotone" dataKey="brake" name="brake" stroke={COLORS.brake} strokeWidth={1.5} fill="url(#brakeGrad1)" dot={false} connectNulls />
              {hasCompare && <Area type="monotone" dataKey="brake2" name="brake2" stroke={COLORS.brake2} strokeWidth={1.5} strokeDasharray="6 3" strokeOpacity={0.6} fill="url(#brakeGrad2)" dot={false} connectNulls />}
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Volante" unit="%" onExpand={() => setExpandedChart('steering')}>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={data} margin={chartMargin}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
              <XAxis {...xAxisConfigToUse} />
              <YAxis {...yAxisConfig} />
              <Tooltip {...tooltipProps} />
              <Line type="monotone" dataKey="steering" name="steering" stroke={COLORS.steering} strokeWidth={1.5} dot={false} connectNulls />
              {hasCompare && <Line type="monotone" dataKey="steering2" name="steering2" stroke={COLORS.steering2} strokeWidth={1.5} strokeDasharray="6 3" strokeOpacity={0.6} dot={false} connectNulls />}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Modal fullscreen */}
      {expandedChart && (
        <ExpandedChartModal
          chartType={expandedChart}
          data={data}
          hasCompare={hasCompare}
          lapLabel={lapLabel}
          compareLapLabel={compareLapLabel}
          tooltipProps={tooltipProps}
          onClose={() => setExpandedChart(null)}
        />
      )}
    </>
  );
}

function ChartCard({ title, subtitle, unit, children, onExpand }) {
  return (
    <div className="glass-card p-5 group cursor-pointer hover:border-delta-accent/40 transition-all relative" onClick={onExpand}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-display font-semibold text-delta-text">{title}</h3>
          {subtitle && <p className="text-xs text-delta-muted mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-delta-muted">{unit}</span>
          <button
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg bg-delta-surface hover:bg-delta-accent/20 text-delta-muted hover:text-delta-accent"
            onClick={(e) => { e.stopPropagation(); onExpand?.(); }}
          >
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
      {children}
      <div className="absolute inset-0 rounded-2xl border-2 border-transparent group-hover:border-delta-accent/20 pointer-events-none transition-colors" />
    </div>
  );
}

// ─── Modal Fullscreen ──────────────────────────────────────────────────────
function ExpandedChartModal({ chartType, data, hasCompare, lapLabel, compareLapLabel, tooltipProps, onClose }) {
  const chartConfigs = {
    speed: {
      title: 'Velocidade',
      unit: 'km/h',
      component: (data) => (
        <LineChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
          <XAxis {...xAxisConfigToUse} />
          <YAxis {...yAxisConfig} />
          <Tooltip {...tooltipProps} />
          <Line type="monotone" dataKey="speed" name="speed" stroke={COLORS.speed} strokeWidth={3} dot={false} connectNulls />
          {hasCompare && <Line type="monotone" dataKey="speed2" name="speed2" stroke={COLORS.speed2} strokeWidth={2} strokeDasharray="6 3" strokeOpacity={0.7} dot={false} connectNulls />}
        </LineChart>
      ),
    },
    throttle: {
      title: 'Acelerador',
      unit: '%',
      component: (data) => (
        <LineChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
          <XAxis {...xAxisConfigToUse} />
          <YAxis {...yAxisConfig} domain={[0, 100]} />
          <Tooltip {...tooltipProps} />
          <Line type="monotone" dataKey="throttle" name="throttle" stroke={COLORS.throttle} strokeWidth={2.5} dot={false} connectNulls />
          {hasCompare && <Line type="monotone" dataKey="throttle2" name="throttle2" stroke={COLORS.throttle2} strokeWidth={2} strokeDasharray="6 3" strokeOpacity={0.6} dot={false} connectNulls />}
        </LineChart>
      ),
    },
    brake: {
      title: 'Freio',
      unit: '%',
      component: (data) => (
        <AreaChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
          <XAxis {...xAxisConfigToUse} />
          <YAxis {...yAxisConfig} domain={[0, 100]} />
          <Tooltip {...tooltipProps} />
          <defs>
            <linearGradient id="brakeGradExpanded1" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COLORS.brake} stopOpacity={0.3} />
              <stop offset="100%" stopColor={COLORS.brake} stopOpacity={0} />
            </linearGradient>
            {hasCompare && (
              <linearGradient id="brakeGradExpanded2" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS.brake2} stopOpacity={0.2} />
                <stop offset="100%" stopColor={COLORS.brake2} stopOpacity={0} />
              </linearGradient>
            )}
          </defs>
          <Area type="monotone" dataKey="brake" name="brake" stroke={COLORS.brake} strokeWidth={2.5} fill="url(#brakeGradExpanded1)" dot={false} connectNulls />
          {hasCompare && <Area type="monotone" dataKey="brake2" name="brake2" stroke={COLORS.brake2} strokeWidth={2} strokeDasharray="6 3" strokeOpacity={0.6} fill="url(#brakeGradExpanded2)" dot={false} connectNulls />}
        </AreaChart>
      ),
    },
    steering: {
      title: 'Volante',
      unit: '%',
      component: (data) => (
        <LineChart data={data} margin={chartMargin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
          <XAxis {...xAxisConfigToUse} />
          <YAxis {...yAxisConfig} />
          <Tooltip {...tooltipProps} />
          <Line type="monotone" dataKey="steering" name="steering" stroke={COLORS.steering} strokeWidth={2.5} dot={false} connectNulls />
          {hasCompare && <Line type="monotone" dataKey="steering2" name="steering2" stroke={COLORS.steering2} strokeWidth={2} strokeDasharray="6 3" strokeOpacity={0.6} dot={false} connectNulls />}
        </LineChart>
      ),
    },
  };

  const config = chartConfigs[chartType];
  if (!config) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-delta-bg/95 backdrop-blur-sm p-4 animate-fade-in">
      <div className="w-full h-full flex flex-col bg-delta-surface/80 backdrop-blur-xl border border-delta-border rounded-3xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-delta-border/50">
          <div>
            <h2 className="font-display font-bold text-2xl text-delta-text">{config.title}</h2>
            <p className="text-sm text-delta-muted mt-1">Clique no gráfico para fechar · Pressione ESC</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-delta-card text-delta-muted hover:text-delta-accent transition-all"
          >
            <X size={24} />
          </button>
        </div>

        {/* Gráfico expandido */}
        <div className="flex-1 overflow-hidden p-6">
          <ResponsiveContainer width="100%" height="100%">
            {config.component(data)}
          </ResponsiveContainer>
        </div>

        {/* Legenda */}
        {hasCompare && (
          <div className="px-6 py-4 border-t border-delta-border/50 flex items-center gap-8 justify-center bg-delta-surface/50">
            <div className="flex items-center gap-2">
              <div className="w-8 h-1 rounded-full" style={{ backgroundColor: COLORS.speed }} />
              <span className="text-sm font-mono text-delta-text">{lapLabel || 'Principal'}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-8 h-1 rounded-full border-2 border-dashed" style={{ borderColor: COLORS.speed2 }} />
              <span className="text-sm font-mono text-delta-muted">{compareLapLabel || 'Comparação'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
