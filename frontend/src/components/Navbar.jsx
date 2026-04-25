import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Map, BarChart3, Bot, Settings } from 'lucide-react';

const NAV_ITEMS = [
  { path: '/', label: 'Sessões', icon: LayoutDashboard },
  { path: '/map', label: 'Mapa', icon: Map },
  { path: '/charts', label: 'Gráficos', icon: BarChart3 },
  { path: '/ai', label: 'IA', icon: Bot },
];

export default function Navbar() {
  const location = useLocation();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 md:fixed md:top-0 md:left-0 md:bottom-0 md:right-auto md:w-64">
      {/* Mobile: bottom bar */}
      <div className="md:hidden flex items-center justify-around bg-delta-surface/95 backdrop-blur-xl border-t border-delta-border py-2 px-4">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <Link
            key={path}
            to={path}
            className={`flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl text-xs transition-all ${
              location.pathname === path
                ? 'text-delta-accent'
                : 'text-delta-muted'
            }`}
          >
            <Icon size={20} />
            <span>{label}</span>
          </Link>
        ))}
      </div>

      {/* Desktop: sidebar */}
      <div className="hidden md:flex flex-col h-full bg-delta-surface/80 backdrop-blur-xl border-r border-delta-border">
        {/* Logo */}
        <div className="p-6 border-b border-delta-border">
          <Link to="/" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-delta-accent to-delta-accent2 flex items-center justify-center">
              <span className="font-display font-black text-delta-bg text-lg">Δ</span>
            </div>
            <div>
              <h1 className="font-display font-bold text-lg text-delta-text leading-tight">
                AMS2 Delta
              </h1>
              <p className="text-[10px] uppercase tracking-[0.2em] text-delta-muted font-medium">
                Telemetria
              </p>
            </div>
          </Link>
        </div>

        {/* Nav links */}
        <div className="flex-1 p-4 space-y-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
            <Link
              key={path}
              to={path}
              className={`nav-link ${location.pathname === path ? 'active' : ''}`}
            >
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          ))}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-delta-border">
          <p className="text-[10px] text-delta-muted text-center font-mono">
            v2.0 · React + FastAPI
          </p>
        </div>
      </div>
    </nav>
  );
}
