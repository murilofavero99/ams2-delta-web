import { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSessions, fetchLapTelemetry } from '../api/client';
import Loading from '../components/Loading';
import { Zap, Gauge, Flag, ChevronDown, Info } from 'lucide-react';

// ─── Paleta de cores por velocidade ───────────────────────────────────────────
function speedColor(speed, minSpeed, maxSpeed) {
  const t = Math.max(0, Math.min(1, (speed - minSpeed) / (maxSpeed - minSpeed)));
  // Azul → Ciano → Verde → Amarelo → Vermelho
  const stops = [
    [0,    [30,  100, 255]],
    [0.25, [0,   200, 255]],
    [0.50, [0,   255, 100]],
    [0.75, [255, 220,   0]],
    [1.0,  [255,  50,  50]],
  ];
  let c1 = stops[0][1], c2 = stops[1][1], lt = 0;
  for (let i = 0; i < stops.length - 1; i++) {
    if (t >= stops[i][0] && t <= stops[i+1][0]) {
      lt = (t - stops[i][0]) / (stops[i+1][0] - stops[i][0]);
      c1 = stops[i][1]; c2 = stops[i+1][1]; break;
    }
  }
  const r = Math.round(c1[0] + (c2[0]-c1[0]) * lt);
  const g = Math.round(c1[1] + (c2[1]-c1[1]) * lt);
  const b = Math.round(c1[2] + (c2[2]-c1[2]) * lt);
  return `rgb(${r},${g},${b})`;
}

// ─── Detecta zonas de freada e aceleração ─────────────────────────────────────
function detectZones(pts) {
  const braking = [], accelerating = [];
  let inBrake = false, inAccel = false;
  let bStart = null, aStart = null;

  for (let i = 1; i < pts.length; i++) {
    const t = pts[i];
    const prev = pts[i - 1];

    // Zona de freada: brake > 30% por pelo menos 3 pontos
    if (t.brake_pct > 30 && !inBrake) {
      inBrake = true; bStart = i;
    } else if (t.brake_pct < 10 && inBrake) {
      inBrake = false;
      const zone = pts.slice(bStart, i);
      if (zone.length >= 3) {
        const mid = zone[Math.floor(zone.length / 2)];
        const maxBrake = Math.max(...zone.map(z => z.brake_pct));
        const speedDrop = zone[0].speed_kmh - zone[zone.length - 1].speed_kmh;
        braking.push({
          px: mid.px, py: mid.py,
          dist: mid.current_lap_distance,
          maxBrake, speedDrop,
          speedEntry: zone[0].speed_kmh,
          speedExit: zone[zone.length - 1].speed_kmh,
        });
      }
    }

    // Zona de aceleração: throttle > 80% após freada
    if (t.throttle_pct > 80 && prev.brake_pct > 20 && !inAccel) {
      inAccel = true; aStart = i;
    } else if (t.throttle_pct < 50 && inAccel) {
      inAccel = false;
      const zone = pts.slice(aStart, i);
      if (zone.length >= 3) {
        const mid = zone[Math.floor(zone.length / 3)];
        accelerating.push({
          px: mid.px, py: mid.py,
          dist: mid.current_lap_distance,
          speedApex: zone[0].speed_kmh,
        });
      }
    }
  }
  return { braking, accelerating };
}

// ─── Normaliza coordenadas pra caber no SVG ────────────────────────────────────
function normalizeCoords(telemetry, width, height, padding = 40) {
  const xs = telemetry.map(t => t.world_x);
  const zs = telemetry.map(t => t.world_z);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minZ = Math.min(...zs), maxZ = Math.max(...zs);
  const rangeX = maxX - minX || 1;
  const rangeZ = maxZ - minZ || 1;
  const scale = Math.min((width - padding*2) / rangeX, (height - padding*2) / rangeZ);
  const offX = (width  - rangeX * scale) / 2;
  const offZ = (height - rangeZ * scale) / 2;
  return telemetry.map(t => ({
    ...t,
    px: offX + (t.world_x - minX) * scale,
    py: offZ + (t.world_z - minZ) * scale,
  }));
}

// ─── Gera path SVG segmentado por cor ─────────────────────────────────────────
function buildColoredSegments(pts, minSpeed, maxSpeed) {
  const segs = [];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i-1], b = pts[i];
    segs.push({ x1: a.px, y1: a.py, x2: b.px, y2: b.py,
      color: speedColor((a.speed_kmh + b.speed_kmh) / 2, minSpeed, maxSpeed) });
  }
  return segs;
}

// ─── Componente principal ──────────────────────────────────────────────────────
export default function TrackMap() {
  const svgRef = useRef(null);
  const [svgSize, setSvgSize] = useState({ w: 800, h: 500 });
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [lastPan, setLastPan] = useState({ x: 0, y: 0 });
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
  const [selectedLap, setSelectedLap] = useState(null);
  const [activeMode, setActiveMode] = useState('speed'); // speed | braking | accel

  const { data: sessions } = useQuery({ queryKey: ['sessions'], queryFn: fetchSessions });

  const { data: telemetry, isLoading } = useQuery({
    queryKey: ['telemetry', selectedSession, selectedLap],
    queryFn: () => fetchLapTelemetry(selectedSession, selectedLap, 5000),
    enabled: !!selectedSession && !!selectedLap,
  });

  // Auto-seleciona primeira sessão/volta
  useEffect(() => {
    if (sessions?.length && !selectedSession) {
      const s = sessions.find(s => s.laps.length > 0) || sessions[0];
      setSelectedSession(s.metadata.session_id);
      const fastest = s.laps.find(l => l.is_fastest) || s.laps[0];
      if (fastest) setSelectedLap(fastest.lap_number);
    }
  }, [sessions]);

  // Mede o container SVG
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setSvgSize({ w: Math.max(width, 300), h: Math.max(height, 300) });
    });
    if (svgRef.current) obs.observe(svgRef.current.parentElement);
    return () => obs.disconnect();
  }, []);

  // Zoom com scroll
  const onWheel = useCallback((e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.88;
    setTransform(t => ({
      scale: Math.max(0.5, Math.min(10, t.scale * factor)),
      x: t.x, y: t.y,
    }));
  }, []);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const onMouseDown = (e) => {
    setIsPanning(true);
    setLastPan({ x: e.clientX, y: e.clientY });
  };
  const onMouseMove = (e) => {
    if (!isPanning) return;
    const dx = e.clientX - lastPan.x, dy = e.clientY - lastPan.y;
    setTransform(t => ({ ...t, x: t.x + dx, y: t.y + dy }));
    setLastPan({ x: e.clientX, y: e.clientY });
  };
  const onMouseUp = () => setIsPanning(false);

  // Touch pan/zoom
  const lastTouchDist = useRef(null);
  const onTouchStart = (e) => {
    if (e.touches.length === 1) {
      setIsPanning(true);
      setLastPan({ x: e.touches[0].clientX, y: e.touches[0].clientY });
    }
  };
  const onTouchMove = (e) => {
    if (e.touches.length === 2) {
      const d = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      if (lastTouchDist.current) {
        const factor = d / lastTouchDist.current;
        setTransform(t => ({ ...t, scale: Math.max(0.5, Math.min(10, t.scale * factor)) }));
      }
      lastTouchDist.current = d;
    } else if (e.touches.length === 1 && isPanning) {
      const dx = e.touches[0].clientX - lastPan.x;
      const dy = e.touches[0].clientY - lastPan.y;
      setTransform(t => ({ ...t, x: t.x + dx, y: t.y + dy }));
      setLastPan({ x: e.touches[0].clientX, y: e.touches[0].clientY });
    }
  };
  const onTouchEnd = () => { setIsPanning(false); lastTouchDist.current = null; };

  // Reset zoom
  const resetZoom = () => setTransform({ x: 0, y: 0, scale: 1 });

  // Prepara dados
  const pts = telemetry && svgSize.w > 0
    ? normalizeCoords(telemetry, svgSize.w, svgSize.h) : [];
  const minSpeed = pts.length ? Math.min(...pts.map(p => p.speed_kmh)) : 0;
  const maxSpeed = pts.length ? Math.max(...pts.map(p => p.speed_kmh)) : 300;
  const segments = pts.length ? buildColoredSegments(pts, minSpeed, maxSpeed) : [];
  const zones = pts.length ? detectZones(pts) : { braking: [], accelerating: [] };

  // Sessão atual
  const currentSession = sessions?.find(s => s.metadata.session_id === selectedSession);
  const currentLapInfo = currentSession?.laps.find(l => l.lap_number === selectedLap);

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] gap-4">
      {/* ── Controles ── */}
      <div className="flex flex-wrap items-center gap-3 animate-fade-in">
        {/* Sessão */}
        <div className="relative">
          <select
            className="appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium text-delta-text focus:outline-none focus:border-delta-accent/50 cursor-pointer"
            value={selectedSession || ''}
            onChange={e => {
              setSelectedSession(e.target.value);
              const s = sessions.find(s => s.metadata.session_id === e.target.value);
              const f = s?.laps.find(l => l.is_fastest) || s?.laps[0];
              if (f) setSelectedLap(f.lap_number);
              resetZoom();
            }}
          >
            {sessions?.map(s => (
              <option key={s.metadata.session_id} value={s.metadata.session_id}>
                {s.metadata.track_location} — {s.metadata.started_at?.slice(0,8)}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
        </div>

        {/* Volta */}
        <div className="relative">
          <select
            className="appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium text-delta-text focus:outline-none focus:border-delta-accent/50 cursor-pointer"
            value={selectedLap || ''}
            onChange={e => { setSelectedLap(Number(e.target.value)); resetZoom(); }}
          >
            {currentSession?.laps.map(l => (
              <option key={l.lap_number} value={l.lap_number}>
                #{l.lap_number} — {formatTime(l.lap_time_s)}{l.is_fastest ? ' ⭐' : ''}
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
        </div>

        {/* Modo */}
        <div className="flex items-center gap-1 bg-delta-card border border-delta-border rounded-xl p-1">
          {[
            { id: 'speed',   label: 'Velocidade', color: 'text-delta-accent' },
            { id: 'braking', label: 'Freadas',    color: 'text-delta-loss'   },
            { id: 'accel',   label: 'Aceleração', color: 'text-delta-gain'   },
          ].map(m => (
            <button
              key={m.id}
              onClick={() => setActiveMode(m.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeMode === m.id
                  ? `bg-delta-surface ${m.color}`
                  : 'text-delta-muted hover:text-delta-text'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Reset zoom */}
        <button onClick={resetZoom} className="btn-ghost text-xs px-3 py-2">
          Reset zoom
        </button>

        {/* Tempo */}
        {currentLapInfo && (
          <div className="ml-auto font-mono text-lg font-bold text-delta-gain">
            {formatTime(currentLapInfo.lap_time_s)}
            {currentLapInfo.is_fastest && <span className="text-xs text-delta-warn ml-2">⭐ BEST</span>}
          </div>
        )}
      </div>

      {/* ── Mapa + Painel ── */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
        {/* SVG Map */}
        <div className="flex-1 glass-card overflow-hidden relative select-none min-h-[300px]">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loading text="Carregando traçado..." />
            </div>
          )}

          {!telemetry && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="text-delta-muted text-sm">Selecione uma sessão e volta</p>
            </div>
          )}

          <svg
            ref={svgRef}
            className={`w-full h-full ${isPanning ? 'cursor-grabbing' : 'cursor-grab'}`}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
          >
            <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}
               style={{ transformOrigin: `${svgSize.w/2}px ${svgSize.h/2}px` }}>

              {/* Traçado colorido por velocidade */}
              {segments.map((seg, i) => (
                <line
                  key={i}
                  x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
                  stroke={seg.color}
                  strokeWidth={4 / transform.scale}
                  strokeLinecap="round"
                />
              ))}

              {/* Zonas de freada */}
              {(activeMode === 'braking' || activeMode === 'speed') &&
                zones.braking.map((z, i) => (
                  <g key={i}>
                    <circle
                      cx={z.px} cy={z.py}
                      r={8 / transform.scale}
                      fill="#ff4466"
                      fillOpacity={0.9}
                      stroke="#0a0a0f"
                      strokeWidth={2 / transform.scale}
                      className="cursor-pointer"
                      onMouseEnter={() => setHoveredPoint({ type: 'brake', ...z })}
                      onMouseLeave={() => setHoveredPoint(null)}
                    />
                    <text
                      x={z.px} y={z.py + 1}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fontSize={7 / transform.scale}
                      fill="white"
                      fontWeight="bold"
                      style={{ pointerEvents: 'none' }}
                    >
                      {i + 1}
                    </text>
                  </g>
                ))
              }

              {/* Zonas de aceleração */}
              {(activeMode === 'accel' || activeMode === 'speed') &&
                zones.accelerating.slice(0, 8).map((z, i) => (
                  <circle
                    key={i}
                    cx={z.px} cy={z.py}
                    r={6 / transform.scale}
                    fill="#00ff88"
                    fillOpacity={0.85}
                    stroke="#0a0a0f"
                    strokeWidth={1.5 / transform.scale}
                    className="cursor-pointer"
                    onMouseEnter={() => setHoveredPoint({ type: 'accel', ...z })}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                ))
              }

              {/* Linha de largada */}
              {pts.length > 0 && (
                <g>
                  <circle cx={pts[0].px} cy={pts[0].py} r={10 / transform.scale}
                    fill="#ffaa00" fillOpacity={0.9} stroke="#0a0a0f" strokeWidth={2 / transform.scale} />
                  <text x={pts[0].px} y={pts[0].py} textAnchor="middle" dominantBaseline="middle"
                    fontSize={8 / transform.scale} fill="#0a0a0f" fontWeight="bold">S</text>
                </g>
              )}
            </g>
          </svg>

          {/* Tooltip hover */}
          {hoveredPoint && (
            <div className="absolute bottom-4 left-4 glass-card px-4 py-3 text-xs font-mono pointer-events-none animate-fade-in">
              {hoveredPoint.type === 'brake' ? (
                <>
                  <p className="text-delta-loss font-bold mb-1">🔴 Freada</p>
                  <p>Entrada: <span className="text-delta-text">{hoveredPoint.speedEntry?.toFixed(0)} km/h</span></p>
                  <p>Saída: <span className="text-delta-text">{hoveredPoint.speedExit?.toFixed(0)} km/h</span></p>
                  <p>Redução: <span className="text-delta-loss">-{hoveredPoint.speedDrop?.toFixed(0)} km/h</span></p>
                  <p>Pressão máx: <span className="text-delta-text">{hoveredPoint.maxBrake?.toFixed(0)}%</span></p>
                </>
              ) : (
                <>
                  <p className="text-delta-gain font-bold mb-1">🟢 Aceleração</p>
                  <p>Vel. saída curva: <span className="text-delta-text">{hoveredPoint.speedApex?.toFixed(0)} km/h</span></p>
                  <p>Distância: <span className="text-delta-text">{hoveredPoint.dist?.toFixed(0)}m</span></p>
                </>
              )}
            </div>
          )}

          {/* Dica de controles */}
          <div className="absolute top-3 right-3 flex items-center gap-1.5 text-xs text-delta-muted/60 font-mono">
            <Info size={10} />
            <span>Scroll = zoom · Arrastar = mover</span>
          </div>
        </div>

        {/* ── Painel lateral de zonas ── */}
        <div className="lg:w-72 glass-card p-4 overflow-y-auto space-y-4">
          {/* Legenda de velocidade */}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3">
              Velocidade
            </h3>
            <div className="flex items-center gap-2 mb-1">
              <div className="h-2 flex-1 rounded-full" style={{
                background: 'linear-gradient(to right, rgb(30,100,255), rgb(0,200,255), rgb(0,255,100), rgb(255,220,0), rgb(255,50,50))'
              }} />
            </div>
            <div className="flex justify-between text-xs font-mono text-delta-muted">
              <span>{minSpeed.toFixed(0)} km/h</span>
              <span>{maxSpeed.toFixed(0)} km/h</span>
            </div>
          </div>

          {/* Zonas de freada */}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-delta-loss inline-block" />
              Freadas ({zones.braking.length})
            </h3>
            <div className="space-y-2">
              {zones.braking.map((z, i) => {
                return (
                  <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl bg-delta-surface/50 text-xs font-mono">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-delta-loss/20 text-delta-loss flex items-center justify-center font-bold text-[10px]">
                        {i+1}
                      </span>
                      <span className="text-delta-muted">{z.dist?.toFixed(0)}m</span>
                    </div>
                    <div className="text-right">
                      <p className="text-delta-text">{z.speedEntry?.toFixed(0)}→{z.speedExit?.toFixed(0)}</p>
                      <p className="text-delta-loss text-[10px]">-{z.speedDrop?.toFixed(0)} km/h</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Pontos de aceleração */}
          <div>
            <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-delta-gain inline-block" />
              Acelerações ({zones.accelerating.length})
            </h3>
            <div className="space-y-2">
              {zones.accelerating.slice(0, 8).map((z, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl bg-delta-surface/50 text-xs font-mono">
                  <span className="text-delta-muted">{z.dist?.toFixed(0)}m</span>
                  <span className="text-delta-gain">{z.speedApex?.toFixed(0)} km/h</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(3);
  return `${m}:${sec.padStart(6, '0')}`;
}
