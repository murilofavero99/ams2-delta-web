import { useState, useRef, useEffect, useCallback, useMemo, createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSessions, fetchLapTelemetry } from '../api/client';
import Loading from '../components/Loading';
import {
  Zap, Gauge, Flag, ChevronDown, Info, Map as MapIcon,
  Layers, GitCompare, Crosshair, Eye, EyeOff, RotateCcw
} from 'lucide-react';

// ═══════════════════════════════════════════════════════════════════════════════
// TRACK PRESETS — coordenadas reais X/Z das pistas com racing line ideal
// ═══════════════════════════════════════════════════════════════════════════════

const TRACK_PRESETS = {
  "Interlagos": {
    name: "Autódromo José Carlos Pace",
    city: "Interlagos, São Paulo",
    length_m: 4309,
    racingLine: [
      {x: 0, z: 0}, {x: 50, z: -5}, {x: 100, z: -12}, {x: 150, z: -25},
      {x: 180, z: -50}, {x: 190, z: -80}, {x: 185, z: -110}, {x: 170, z: -135},
      {x: 155, z: -150}, {x: 140, z: -155}, {x: 120, z: -148},
      {x: 90, z: -130}, {x: 70, z: -110}, {x: 55, z: -85},
      {x: 50, z: -60}, {x: 48, z: -30}, {x: 45, z: 0}, {x: 40, z: 30},
      {x: 35, z: 60}, {x: 30, z: 90},
      {x: 25, z: 110}, {x: 15, z: 125}, {x: 0, z: 135}, {x: -20, z: 140},
      {x: -40, z: 138}, {x: -55, z: 130}, {x: -65, z: 115}, {x: -70, z: 95},
      {x: -75, z: 70}, {x: -80, z: 50}, {x: -88, z: 35}, {x: -100, z: 25},
      {x: -115, z: 20}, {x: -130, z: 22}, {x: -140, z: 30},
      {x: -145, z: 45}, {x: -142, z: 60}, {x: -135, z: 75},
      {x: -125, z: 85}, {x: -110, z: 88}, {x: -95, z: 82},
      {x: -80, z: 70}, {x: -65, z: 55}, {x: -55, z: 38}, {x: -48, z: 20},
      {x: -42, z: 0}, {x: -38, z: -15}, {x: -30, z: -25},
      {x: -18, z: -20}, {x: -8, z: -12}, {x: 0, z: 0},
    ],
    curves: [
      { name: "S do Senna", dist: 200, type: "chicane" },
      { name: "Curva do Sol", dist: 600, type: "curve" },
      { name: "Reta Oposta", dist: 1000, type: "straight" },
      { name: "Descida do Lago", dist: 1400, type: "complex" },
      { name: "Ferradura", dist: 1900, type: "hairpin" },
      { name: "Pinheirinho", dist: 2400, type: "curve" },
      { name: "Bico de Pato", dist: 2700, type: "curve" },
      { name: "Mergulho", dist: 3100, type: "curve" },
      { name: "Junção", dist: 3600, type: "curve" },
      { name: "Subida dos Boxes", dist: 4000, type: "curve" },
    ],
  },
  "Montreal": {
    name: "Circuit Gilles Villeneuve",
    city: "Île Notre-Dame, Montreal",
    length_m: 4361,
    racingLine: [
      {x: 0, z: 0}, {x: 30, z: 2}, {x: 60, z: 5}, {x: 90, z: 3},
      {x: 110, z: -5}, {x: 120, z: -18}, {x: 125, z: -30}, {x: 118, z: -42},
      {x: 110, z: -48}, {x: 100, z: -50},
      {x: 80, z: -55}, {x: 65, z: -62}, {x: 55, z: -72}, {x: 50, z: -85},
      {x: 48, z: -100}, {x: 42, z: -110}, {x: 32, z: -118},
      {x: 20, z: -120}, {x: 8, z: -115},
      {x: 0, z: -105}, {x: -5, z: -90}, {x: -2, z: -75},
      {x: 5, z: -65}, {x: 15, z: -58},
      {x: 30, z: -55}, {x: 45, z: -55}, {x: 60, z: -58},
      {x: 72, z: -65}, {x: 78, z: -75}, {x: 80, z: -88},
      {x: 75, z: -98}, {x: 65, z: -105}, {x: 52, z: -108},
      {x: 35, z: -105}, {x: 15, z: -100}, {x: -5, z: -95},
      {x: -25, z: -90}, {x: -45, z: -85}, {x: -65, z: -80},
      {x: -80, z: -72}, {x: -90, z: -62}, {x: -95, z: -50},
      {x: -92, z: -38}, {x: -85, z: -28},
      {x: -75, z: -20}, {x: -60, z: -15}, {x: -40, z: -10},
      {x: -20, z: -5}, {x: 0, z: 0},
    ],
    curves: [
      { name: "Turn 1-2 (Chicane)", dist: 300, type: "chicane" },
      { name: "Turn 3", dist: 600, type: "curve" },
      { name: "Turn 4-5", dist: 900, type: "curve" },
      { name: "Turn 6-7", dist: 1250, type: "chicane" },
      { name: "Turn 8-9", dist: 1600, type: "curve" },
      { name: "L'Epingle", dist: 1950, type: "hairpin" },
      { name: "Droit du Casino", dist: 2800, type: "straight" },
      { name: "Turn 13-14", dist: 3800, type: "chicane" },
    ],
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// UTILIDADES
// ═══════════════════════════════════════════════════════════════════════════════

function speedColor(speed, minSpeed, maxSpeed) {
  const t = Math.max(0, Math.min(1, (speed - minSpeed) / (maxSpeed - minSpeed)));
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

function normalizeCoords(telemetry, width, height, padding = 50) {
  const xs = telemetry.map(t => t.world_x ?? t.x);
  const zs = telemetry.map(t => t.world_z ?? t.z);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minZ = Math.min(...zs), maxZ = Math.max(...zs);
  const rangeX = maxX - minX || 1;
  const rangeZ = maxZ - minZ || 1;
  const scale = Math.min((width - padding*2) / rangeX, (height - padding*2) / rangeZ);
  const offX = (width  - rangeX * scale) / 2;
  const offZ = (height - rangeZ * scale) / 2;
  return telemetry.map(t => ({
    ...t,
    px: offX + ((t.world_x ?? t.x) - minX) * scale,
    py: offZ + ((t.world_z ?? t.z) - minZ) * scale,
  }));
}

function buildColoredSegments(pts, minSpeed, maxSpeed) {
  const segs = [];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i-1], b = pts[i];
    const color = speedColor((a.speed_kmh + b.speed_kmh) / 2, minSpeed, maxSpeed);
    segs.push({ x1: a.px, y1: a.py, x2: b.px, y2: b.py, color });
  }
  return segs;
}

function findNearestPoint(pts, distance) {
  if (!pts || pts.length === 0) return null;
  let best = pts[0], bestDiff = Infinity;
  for (const p of pts) {
    const diff = Math.abs((p.current_lap_distance ?? 0) - distance);
    if (diff < bestDiff) { bestDiff = diff; best = p; }
  }
  return bestDiff < 80 ? best : null;
}

function formatTime(s) {
  if (!s || s <= 0) return '—';
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(3);
  return `${m}:${sec.padStart(6, '0')}`;
}


// ═══════════════════════════════════════════════════════════════════════════════
// SYNC CHART — gráfico de velocidade sincronizado com o mapa via hover
// ═══════════════════════════════════════════════════════════════════════════════

function SyncChart({ pts1, pts2, hoveredDistance, onHoverDistance, label1, label2 }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  const data1 = useMemo(() => {
    if (!pts1) return [];
    const step = Math.max(1, Math.floor(pts1.length / 400));
    return pts1.filter((_, i) => i % step === 0);
  }, [pts1]);

  const data2 = useMemo(() => {
    if (!pts2) return [];
    const step = Math.max(1, Math.floor(pts2.length / 400));
    return pts2.filter((_, i) => i % step === 0);
  }, [pts2]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || data1.length === 0) return;

    const rect = container.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    canvas.width = w * 2;
    canvas.height = h * 2;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;

    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);

    const pad = { top: 22, right: 15, bottom: 25, left: 42 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;

    ctx.clearRect(0, 0, w, h);

    // Fundo
    ctx.fillStyle = 'rgba(26, 26, 38, 0.5)';
    ctx.beginPath();
    ctx.roundRect(0, 0, w, h, 12);
    ctx.fill();

    // Eixos
    const allSpeeds = [...data1.map(d => d.speed_kmh), ...(data2.length ? data2.map(d => d.speed_kmh) : [])];
    const minS = Math.min(...allSpeeds) - 10;
    const maxS = Math.max(...allSpeeds) + 10;
    const maxDist = Math.max(...data1.map(d => d.current_lap_distance));

    const toX = d => pad.left + (d / maxDist) * cw;
    const toY = s => pad.top + ch - ((s - minS) / (maxS - minS)) * ch;

    // Grid
    ctx.strokeStyle = '#1e1e2e';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (ch / 4) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
      const speed = maxS - ((maxS - minS) / 4) * i;
      ctx.fillStyle = '#6b6b8a';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`${speed.toFixed(0)}`, pad.left - 5, y + 3);
    }

    // X labels
    ctx.textAlign = 'center';
    for (let d = 0; d <= maxDist; d += 1000) {
      ctx.fillStyle = '#6b6b8a';
      ctx.fillText(`${(d/1000).toFixed(0)}km`, toX(d), h - 5);
    }

    // Volta 2 (comparação)
    if (data2.length > 0) {
      ctx.strokeStyle = '#7eaaff';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([6, 4]);
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      data2.forEach((d, i) => {
        const x = toX(d.current_lap_distance), y = toY(d.speed_kmh);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    }

    // Volta 1 (principal, colorida)
    ctx.lineWidth = 1.8;
    for (let i = 1; i < data1.length; i++) {
      const a = data1[i-1], b = data1[i];
      ctx.strokeStyle = speedColor((a.speed_kmh + b.speed_kmh) / 2, minS, maxS);
      ctx.beginPath();
      ctx.moveTo(toX(a.current_lap_distance), toY(a.speed_kmh));
      ctx.lineTo(toX(b.current_lap_distance), toY(b.speed_kmh));
      ctx.stroke();
    }

    // Hover line
    if (hoveredDistance !== null && hoveredDistance >= 0) {
      const hx = toX(hoveredDistance);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(hx, pad.top); ctx.lineTo(hx, h - pad.bottom); ctx.stroke();
      ctx.setLineDash([]);

      const c1 = findNearestPoint(data1, hoveredDistance);
      if (c1) {
        ctx.fillStyle = '#00d4ff';
        ctx.font = 'bold 10px "JetBrains Mono", monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`${c1.speed_kmh.toFixed(0)} km/h`, hx + 5, pad.top + 12);

        // Dot on the line
        ctx.beginPath();
        ctx.arc(toX(c1.current_lap_distance), toY(c1.speed_kmh), 3, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
      }
      if (data2.length > 0) {
        const c2 = findNearestPoint(data2, hoveredDistance);
        if (c2) {
          ctx.fillStyle = '#7eaaff';
          ctx.font = 'bold 10px "JetBrains Mono", monospace';
          ctx.fillText(`${c2.speed_kmh.toFixed(0)} km/h`, hx + 5, pad.top + 24);
        }
      }
    }

    // Title
    ctx.fillStyle = '#6b6b8a';
    ctx.font = '10px system-ui';
    ctx.textAlign = 'left';
    ctx.fillText('Velocidade × Distância', pad.left, 14);

    // Legend
    if (label1) {
      ctx.fillStyle = '#00d4ff';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`Volta ${label1}`, w - pad.right, 14);
    }
    if (label2 && data2.length > 0) {
      ctx.fillStyle = '#7eaaff';
      ctx.fillText(`Volta ${label2}`, w - pad.right, 26);
    }

  }, [data1, data2, hoveredDistance, label1, label2]);

  const handleMouseMove = (e) => {
    if (!containerRef.current || data1.length === 0) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pad = { left: 42, right: 15 };
    const cw = rect.width - pad.left - pad.right;
    const maxDist = Math.max(...data1.map(d => d.current_lap_distance));
    const dist = ((x - pad.left) / cw) * maxDist;
    if (dist >= 0 && dist <= maxDist) onHoverDistance?.(dist);
  };

  return (
    <div ref={containerRef} className="w-full h-full relative cursor-crosshair"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => onHoverDistance?.(null)}
    >
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTE PRINCIPAL
// ═══════════════════════════════════════════════════════════════════════════════

export default function TrackMap() {
  const svgRef = useRef(null);
  const [svgSize, setSvgSize] = useState({ w: 800, h: 500 });
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [lastPan, setLastPan] = useState({ x: 0, y: 0 });
  const [hoveredPoint, setHoveredPoint] = useState(null);
  const [hoveredDistance, setHoveredDistance] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
  const [selectedLap, setSelectedLap] = useState(null);
  const [compareLap, setCompareLap] = useState(null);
  const [showRacingLine, setShowRacingLine] = useState(true);
  const [showCurveLabels, setShowCurveLabels] = useState(true);

  const { data: sessions } = useQuery({ queryKey: ['sessions'], queryFn: fetchSessions });

  const { data: telemetry, isLoading } = useQuery({
    queryKey: ['telemetry', selectedSession, selectedLap],
    queryFn: () => fetchLapTelemetry(selectedSession, selectedLap, 5000),
    enabled: !!selectedSession && !!selectedLap,
  });

  const { data: compareTelemetry } = useQuery({
    queryKey: ['telemetry', selectedSession, compareLap],
    queryFn: () => fetchLapTelemetry(selectedSession, compareLap, 5000),
    enabled: !!selectedSession && !!compareLap,
  });

  // Auto-seleciona
  useEffect(() => {
    if (sessions?.length && !selectedSession) {
      const s = sessions.find(s => s.laps.length > 0) || sessions[0];
      setSelectedSession(s.metadata.session_id);
      const fastest = s.laps.find(l => l.is_fastest) || s.laps[0];
      if (fastest) setSelectedLap(fastest.lap_number);
    }
  }, [sessions]);

  // Resize observer
  useEffect(() => {
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setSvgSize({ w: Math.max(width, 300), h: Math.max(height, 300) });
    });
    if (svgRef.current) obs.observe(svgRef.current.parentElement);
    return () => obs.disconnect();
  }, []);

  // Wheel zoom
  const onWheel = useCallback((e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.88;
    setTransform(t => ({ scale: Math.max(0.5, Math.min(10, t.scale * factor)), x: t.x, y: t.y }));
  }, []);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  // Pan handlers
  const onMouseDown = (e) => { setIsPanning(true); setLastPan({ x: e.clientX, y: e.clientY }); };
  const onMouseMove = (e) => {
    if (!isPanning) return;
    setTransform(t => ({ ...t, x: t.x + e.clientX - lastPan.x, y: t.y + e.clientY - lastPan.y }));
    setLastPan({ x: e.clientX, y: e.clientY });
  };
  const onMouseUp = () => setIsPanning(false);

  // Touch
  const lastTouchDist = useRef(null);
  const onTouchStart = (e) => {
    if (e.touches.length === 1) { setIsPanning(true); setLastPan({ x: e.touches[0].clientX, y: e.touches[0].clientY }); }
  };
  const onTouchMove = (e) => {
    if (e.touches.length === 2) {
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      if (lastTouchDist.current) {
        setTransform(t => ({ ...t, scale: Math.max(0.5, Math.min(10, t.scale * d / lastTouchDist.current)) }));
      }
      lastTouchDist.current = d;
    } else if (e.touches.length === 1 && isPanning) {
      setTransform(t => ({ ...t, x: t.x + e.touches[0].clientX - lastPan.x, y: t.y + e.touches[0].clientY - lastPan.y }));
      setLastPan({ x: e.touches[0].clientX, y: e.touches[0].clientY });
    }
  };
  const onTouchEnd = () => { setIsPanning(false); lastTouchDist.current = null; };
  const resetZoom = () => setTransform({ x: 0, y: 0, scale: 1 });

  // ─── Dados processados ───
  const pts = useMemo(() =>
    telemetry && svgSize.w > 0 ? normalizeCoords(telemetry, svgSize.w, svgSize.h) : [],
  [telemetry, svgSize]);

  const comparePts = useMemo(() =>
    compareTelemetry && svgSize.w > 0 ? normalizeCoords(compareTelemetry, svgSize.w, svgSize.h) : [],
  [compareTelemetry, svgSize]);

  const minSpeed = pts.length ? Math.min(...pts.map(p => p.speed_kmh)) : 0;
  const maxSpeed = pts.length ? Math.max(...pts.map(p => p.speed_kmh)) : 300;

  const segments = useMemo(() =>
    pts.length ? buildColoredSegments(pts, minSpeed, maxSpeed) : [],
  [pts, minSpeed, maxSpeed]);

  const compareSegments = useMemo(() => {
    if (!comparePts.length) return [];
    const cMin = Math.min(...comparePts.map(p => p.speed_kmh));
    const cMax = Math.max(...comparePts.map(p => p.speed_kmh));
    return buildColoredSegments(comparePts, cMin, cMax);
  }, [comparePts]);

  // Preset match
  const currentSession = sessions?.find(s => s.metadata.session_id === selectedSession);
  const trackName = currentSession?.metadata.track_location || '';
  const matchedPreset = useMemo(() => {
    for (const [key, preset] of Object.entries(TRACK_PRESETS)) {
      if (trackName.toLowerCase().includes(key.toLowerCase())) return preset;
    }
    return null;
  }, [trackName]);

  // Racing line
  const racingLinePts = useMemo(() => {
    if (!matchedPreset || !showRacingLine) return [];
    return normalizeCoords(
      matchedPreset.racingLine.map(p => ({ world_x: p.x, world_z: p.z })),
      svgSize.w, svgSize.h, 60
    );
  }, [matchedPreset, showRacingLine, svgSize]);

  // Hover sync
  const hoveredMapPoint = useMemo(() => {
    if (hoveredDistance === null || !pts.length) return null;
    return findNearestPoint(pts, hoveredDistance);
  }, [hoveredDistance, pts]);

  const hoveredComparePoint = useMemo(() => {
    if (hoveredDistance === null || !comparePts.length) return null;
    return findNearestPoint(comparePts, hoveredDistance);
  }, [hoveredDistance, comparePts]);

  // SVG hover → distance
  const handleSvgHover = (e) => {
    if (isPanning || !pts.length) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const mx = (e.clientX - rect.left - transform.x) / transform.scale;
    const my = (e.clientY - rect.top - transform.y) / transform.scale;
    let bestDist = Infinity, bestPt = null;
    for (const p of pts) {
      const d = Math.hypot(p.px - mx, p.py - my);
      if (d < bestDist) { bestDist = d; bestPt = p; }
    }
    if (bestDist < 30 / transform.scale && bestPt) {
      setHoveredDistance(bestPt.current_lap_distance);
      setHoveredPoint(bestPt);
    } else {
      setHoveredPoint(null);
    }
  };

  const currentLapInfo = currentSession?.laps.find(l => l.lap_number === selectedLap);
  const compareLapInfo = currentSession?.laps.find(l => l.lap_number === compareLap);

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] gap-4">
      {/* ═══ Header ═══ */}
      <header className="animate-fade-in">
        <h1 className="font-display font-extrabold text-3xl md:text-4xl text-delta-text flex items-center gap-3">
          <MapIcon className="text-delta-accent" size={32} />
          Mapa da Pista
        </h1>
        <p className="text-delta-muted mt-1">
          Traçado, racing line ideal e comparação visual entre voltas
        </p>
      </header>

      {/* ═══ Controles ═══ */}
      <div className="flex flex-wrap items-center gap-3 animate-slide-up">
        {/* Sessão */}
        <Selector value={selectedSession || ''} onChange={v => {
          setSelectedSession(v);
          const s = sessions.find(s => s.metadata.session_id === v);
          const f = s?.laps.find(l => l.is_fastest) || s?.laps[0];
          if (f) setSelectedLap(f.lap_number);
          setCompareLap(null); resetZoom();
        }}>
          {sessions?.map(s => (
            <option key={s.metadata.session_id} value={s.metadata.session_id}>
              {s.metadata.track_location} — {s.metadata.started_at?.slice(0,8)}
            </option>
          ))}
        </Selector>

        {/* Volta */}
        <Selector value={selectedLap || ''} onChange={v => { setSelectedLap(Number(v)); resetZoom(); }}>
          {currentSession?.laps.map(l => (
            <option key={l.lap_number} value={l.lap_number}>
              #{l.lap_number} — {formatTime(l.lap_time_s)}{l.is_fastest ? ' ⭐' : ''}
            </option>
          ))}
        </Selector>

        {/* Comparar */}
        <Selector value={compareLap || ''} onChange={v => setCompareLap(v ? Number(v) : null)} muted>
          <option value="">Comparar com...</option>
          {currentSession?.laps.filter(l => l.lap_number !== selectedLap).map(l => (
            <option key={l.lap_number} value={l.lap_number}>
              #{l.lap_number} — {formatTime(l.lap_time_s)}{l.is_fastest ? ' ⭐' : ''}
            </option>
          ))}
        </Selector>

        {compareLap && (
          <button onClick={() => setCompareLap(null)} className="text-xs text-delta-muted hover:text-delta-loss transition-colors">
            Limpar
          </button>
        )}

        <div className="hidden lg:block w-px h-6 bg-delta-border" />

        {/* Toggles */}
        <div className="flex items-center gap-1 bg-delta-card border border-delta-border rounded-xl p-1">
          {matchedPreset && (
            <ToggleBtn active={showRacingLine} onClick={() => setShowRacingLine(!showRacingLine)}
              icon={Crosshair} label="Racing Line" activeColor="text-delta-warn" />
          )}
          <ToggleBtn active={showCurveLabels} onClick={() => setShowCurveLabels(!showCurveLabels)}
            icon={Flag} label="Curvas" activeColor="text-delta-accent" />
        </div>

        <button onClick={resetZoom} className="btn-ghost text-xs px-3 py-2 flex items-center gap-1.5">
          <RotateCcw size={12} /> Reset
        </button>

        {/* Tempos */}
        {currentLapInfo && (
          <div className="ml-auto flex items-center gap-3">
            <div className="font-mono text-lg font-bold text-delta-gain">
              {formatTime(currentLapInfo.lap_time_s)}
              {currentLapInfo.is_fastest && <span className="text-xs text-delta-warn ml-2">⭐ BEST</span>}
            </div>
            {compareLapInfo && (
              <div className="font-mono text-sm text-delta-muted">
                vs {formatTime(compareLapInfo.lap_time_s)}
                <span className={`ml-1 font-bold ${
                  compareLapInfo.lap_time_s > currentLapInfo.lap_time_s ? 'text-delta-gain' : 'text-delta-loss'
                }`}>
                  ({(currentLapInfo.lap_time_s - compareLapInfo.lap_time_s) > 0 ? '+' : ''}
                  {(currentLapInfo.lap_time_s - compareLapInfo.lap_time_s).toFixed(3)}s)
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ═══ Mapa + Painel ═══ */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
        {/* SVG Map */}
        <div className="flex-1 glass-card overflow-hidden relative select-none min-h-[300px]">
          {isLoading && <div className="absolute inset-0 flex items-center justify-center z-10"><Loading text="Carregando traçado..." /></div>}
          {!telemetry && !isLoading && <div className="absolute inset-0 flex items-center justify-center"><p className="text-delta-muted text-sm">Selecione uma sessão e volta</p></div>}

          <svg ref={svgRef}
            className={`w-full h-full ${isPanning ? 'cursor-grabbing' : 'cursor-crosshair'}`}
            onMouseDown={onMouseDown}
            onMouseMove={(e) => { onMouseMove(e); handleSvgHover(e); }}
            onMouseUp={onMouseUp}
            onMouseLeave={() => { onMouseUp(); setHoveredPoint(null); }}
            onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}
          >
            <g transform={`translate(${transform.x},${transform.y}) scale(${transform.scale})`}
               style={{ transformOrigin: `${svgSize.w/2}px ${svgSize.h/2}px` }}>

              {/* Racing Line ideal */}
              {racingLinePts.length > 1 && (
                <polyline
                  points={racingLinePts.map(p => `${p.px},${p.py}`).join(' ')}
                  fill="none" stroke="#ffaa00" strokeWidth={6 / transform.scale}
                  strokeLinecap="round" strokeLinejoin="round"
                  strokeDasharray={`${8/transform.scale} ${4/transform.scale}`}
                  opacity={0.3}
                />
              )}

              {/* Comparação (volta 2) — opacidade mais baixa */}
              {compareSegments.map((seg, i) => (
                <line key={`c-${i}`}
                  x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
                  stroke={seg.color} strokeWidth={3 / transform.scale}
                  strokeLinecap="round" opacity={0.35}
                />
              ))}

              {/* Volta principal — colorida por velocidade */}
              {segments.map((seg, i) => (
                <line key={i}
                  x1={seg.x1} y1={seg.y1} x2={seg.x2} y2={seg.y2}
                  stroke={seg.color} strokeWidth={4 / transform.scale}
                  strokeLinecap="round"
                />
              ))}

              {/* Labels de curvas do preset */}
              {showCurveLabels && matchedPreset && pts.length > 0 && matchedPreset.curves.map((curve, i) => {
                const pt = findNearestPoint(pts, curve.dist);
                if (!pt) return null;
                return (
                  <g key={`cv-${i}`}>
                    <circle cx={pt.px} cy={pt.py} r={5 / transform.scale}
                      fill="none" stroke="#ffaa00" strokeWidth={1.5 / transform.scale}
                      strokeDasharray={`${2/transform.scale} ${2/transform.scale}`}
                    />
                    <text x={pt.px + 8/transform.scale} y={pt.py - 6/transform.scale}
                      fontSize={9 / transform.scale} fill="#ffaa00" fontFamily="system-ui"
                      fontWeight="600" style={{ pointerEvents: 'none' }}
                    >
                      {curve.name}
                    </text>
                  </g>
                );
              })}

              {/* Largada */}
              {pts.length > 0 && (
                <g>
                  <circle cx={pts[0].px} cy={pts[0].py} r={10 / transform.scale}
                    fill="#ffaa00" fillOpacity={0.9} stroke="#0a0a0f" strokeWidth={2 / transform.scale} />
                  <text x={pts[0].px} y={pts[0].py} textAnchor="middle" dominantBaseline="middle"
                    fontSize={8 / transform.scale} fill="#0a0a0f" fontWeight="bold">S</text>
                </g>
              )}

              {/* ═══ Hover markers sincronizados ═══ */}
              {hoveredMapPoint && (
                <g>
                  <circle cx={hoveredMapPoint.px} cy={hoveredMapPoint.py}
                    r={14 / transform.scale} fill="none" stroke="#ffffff"
                    strokeWidth={2 / transform.scale} opacity={0.8}
                  >
                    <animate attributeName="r" from={10/transform.scale} to={18/transform.scale}
                      dur="1s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.8" to="0.2"
                      dur="1s" repeatCount="indefinite" />
                  </circle>
                  <circle cx={hoveredMapPoint.px} cy={hoveredMapPoint.py}
                    r={4 / transform.scale} fill="#ffffff" />
                </g>
              )}
              {hoveredComparePoint && (
                <g>
                  <circle cx={hoveredComparePoint.px} cy={hoveredComparePoint.py}
                    r={8 / transform.scale} fill="none" stroke="#7eaaff"
                    strokeWidth={1.5 / transform.scale}
                    strokeDasharray={`${3/transform.scale} ${2/transform.scale}`} />
                  <circle cx={hoveredComparePoint.px} cy={hoveredComparePoint.py}
                    r={3 / transform.scale} fill="#7eaaff" />
                </g>
              )}
            </g>
          </svg>

          {/* Tooltip */}
          {hoveredPoint && (
            <div className="absolute bottom-4 left-4 glass-card px-4 py-3 text-xs font-mono pointer-events-none animate-fade-in space-y-1">
              <p className="text-delta-accent font-bold mb-1.5">📍 {hoveredPoint.current_lap_distance?.toFixed(0)}m</p>
              <p>Velocidade: <span className="text-delta-text font-semibold">{hoveredPoint.speed_kmh?.toFixed(1)} km/h</span></p>
              <p>Acelerador: <span className="text-delta-gain">{hoveredPoint.throttle_pct?.toFixed(0)}%</span></p>
              <p>Freio: <span className="text-delta-loss">{hoveredPoint.brake_pct?.toFixed(0)}%</span></p>
              <p>Marcha: <span className="text-delta-text">{hoveredPoint.gear}</span></p>
              {hoveredComparePoint && (
                <div className="border-t border-delta-border/50 mt-1.5 pt-1.5">
                  <p className="text-[#7eaaff] font-bold mb-1">Comparação</p>
                  <p>Vel: <span className="text-[#7eaaff]">{hoveredComparePoint.speed_kmh?.toFixed(1)} km/h</span></p>
                  <p className={`font-bold ${
                    hoveredPoint.speed_kmh > hoveredComparePoint.speed_kmh ? 'text-delta-gain' : 'text-delta-loss'
                  }`}>
                    Δ {(hoveredPoint.speed_kmh - hoveredComparePoint.speed_kmh).toFixed(1)} km/h
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Legends */}
          <div className="absolute top-3 left-3 space-y-1">
            {matchedPreset && showRacingLine && (
              <div className="flex items-center gap-1.5 bg-delta-bg/80 backdrop-blur-sm rounded-lg px-2 py-1 text-[10px] font-mono">
                <div className="w-4 h-0 border-t-2 border-dashed border-[#ffaa00] opacity-50" />
                <span className="text-delta-warn/70">Racing Line</span>
              </div>
            )}
            {compareLap && (
              <div className="flex items-center gap-1.5 bg-delta-bg/80 backdrop-blur-sm rounded-lg px-2 py-1 text-[10px] font-mono">
                <div className="w-4 h-0.5 bg-[#7eaaff] rounded-full opacity-50" />
                <span className="text-[#7eaaff]/70">Volta #{compareLap}</span>
              </div>
            )}
          </div>

          <div className="absolute top-3 right-3 flex items-center gap-1.5 text-xs text-delta-muted/60 font-mono">
            <Info size={10} />
            <span>Scroll=zoom · Arrastar=mover · Hover=sincroniza gráfico</span>
          </div>
        </div>

        {/* ═══ Painel lateral ═══ */}
        <div className="lg:w-80 flex flex-col gap-4 min-h-0 overflow-y-auto">
          {/* Velocidade legenda */}
          <div className="glass-card p-4">
            <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3">Velocidade</h3>
            <div className="h-2 flex-1 rounded-full mb-1" style={{
              background: 'linear-gradient(to right, rgb(30,100,255), rgb(0,200,255), rgb(0,255,100), rgb(255,220,0), rgb(255,50,50))'
            }} />
            <div className="flex justify-between text-xs font-mono text-delta-muted">
              <span>{minSpeed.toFixed(0)} km/h</span>
              <span>{maxSpeed.toFixed(0)} km/h</span>
            </div>
          </div>

          {/* Preset info com curvas clicáveis */}
          {matchedPreset && (
            <div className="glass-card p-4">
              <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3 flex items-center gap-2">
                <Layers size={12} className="text-delta-accent" />
                {matchedPreset.name}
              </h3>
              <p className="text-[10px] text-delta-muted mb-3">{matchedPreset.city} · {matchedPreset.length_m}m</p>
              <div className="space-y-1">
                {matchedPreset.curves.map((c, i) => (
                  <button key={i}
                    className={`w-full flex items-center justify-between py-1.5 px-2 rounded-lg text-xs font-mono transition-colors cursor-pointer ${
                      hoveredDistance !== null && Math.abs(hoveredDistance - c.dist) < 150
                        ? 'bg-delta-accent/10 text-delta-accent'
                        : 'hover:bg-delta-surface/50 text-delta-warn'
                    }`}
                    onClick={() => setHoveredDistance(c.dist)}
                    onMouseEnter={() => setHoveredDistance(c.dist)}
                  >
                    <span>{c.name}</span>
                    <span className="text-delta-muted text-[10px]">{c.dist}m</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Gráfico sincronizado */}
          {pts.length > 0 && (
            <div className="glass-card p-0 flex-1 min-h-[180px] overflow-hidden">
              <SyncChart
                pts1={telemetry}
                pts2={compareTelemetry}
                hoveredDistance={hoveredDistance}
                onHoverDistance={setHoveredDistance}
                label1={`#${selectedLap}`}
                label2={compareLap ? `#${compareLap}` : null}
              />
            </div>
          )}

          {/* Delta comparação */}
          {compareLap && currentLapInfo && compareLapInfo && (
            <div className="glass-card p-4">
              <h3 className="text-xs uppercase tracking-widest text-delta-muted font-medium mb-3 flex items-center gap-2">
                <GitCompare size={12} className="text-delta-accent" />
                Comparação
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center p-3 rounded-xl bg-delta-surface/50">
                  <p className="text-[10px] text-delta-accent mb-1">Volta #{selectedLap}</p>
                  <p className="font-mono font-bold text-delta-text">{formatTime(currentLapInfo.lap_time_s)}</p>
                </div>
                <div className="text-center p-3 rounded-xl bg-delta-surface/50">
                  <p className="text-[10px] text-[#7eaaff] mb-1">Volta #{compareLap}</p>
                  <p className="font-mono font-bold text-delta-text">{formatTime(compareLapInfo.lap_time_s)}</p>
                </div>
              </div>
              <div className="mt-3 text-center">
                <span className={`font-mono font-bold text-lg ${
                  currentLapInfo.lap_time_s < compareLapInfo.lap_time_s ? 'text-delta-gain' : 'text-delta-loss'
                }`}>
                  Δ {(currentLapInfo.lap_time_s - compareLapInfo.lap_time_s) > 0 ? '+' : ''}
                  {(currentLapInfo.lap_time_s - compareLapInfo.lap_time_s).toFixed(3)}s
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// SUBCOMPONENTES
// ═══════════════════════════════════════════════════════════════════════════════

function Selector({ value, onChange, children, muted }) {
  return (
    <div className="relative">
      <select
        className={`appearance-none bg-delta-card border border-delta-border rounded-xl px-4 py-2.5 pr-9 text-sm font-medium focus:outline-none focus:border-delta-accent/50 cursor-pointer ${
          muted ? 'text-delta-muted' : 'text-delta-text'
        }`}
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {children}
      </select>
      <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-delta-muted pointer-events-none" />
    </div>
  );
}

function ToggleBtn({ active, onClick, icon: Icon, label, activeColor }) {
  return (
    <button onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 ${
        active ? `bg-delta-surface ${activeColor}` : 'text-delta-muted hover:text-delta-text'
      }`}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}
