import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import SessionDetail from './pages/SessionDetail';
import TrackMap from './pages/TrackMap';
import Charts from './pages/Charts';
import AIAnalysis from './pages/AIAnalysis';

export default function App() {
  return (
    <div className="noise-bg min-h-screen">
      <Navbar />
      <main className="pb-20 md:pb-0 md:pl-64">
        <div className="max-w-6xl mx-auto px-4 md:px-8 py-6 md:py-10">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/session/:sessionId" element={<SessionDetail />} />
            <Route path="/map" element={<TrackMap />} />
            <Route path="/charts" element={<Charts />} />
            <Route path="/ai" element={<AIAnalysis />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
