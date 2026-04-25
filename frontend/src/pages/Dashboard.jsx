import { useQuery } from '@tanstack/react-query';
import { FolderOpen } from 'lucide-react';
import { fetchSessions } from '../api/client';
import SessionCard from '../components/SessionCard';
import Loading, { EmptyState } from '../components/Loading';

export default function Dashboard() {
  const { data: sessions, isLoading, error } = useQuery({
    queryKey: ['sessions'],
    queryFn: fetchSessions,
  });

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="mb-8 animate-fade-in">
        <h1 className="font-display font-extrabold text-4xl md:text-5xl text-delta-text mb-2">
          Suas Sessões
        </h1>
        <p className="text-delta-muted text-lg">
          Analise sua telemetria e melhore seus tempos
        </p>
      </header>

      {/* Content */}
      {isLoading && <Loading text="Carregando sessões..." />}

      {error && (
        <div className="glass-card p-6 border-delta-loss/30">
          <p className="text-delta-loss font-medium">Erro ao carregar sessões</p>
          <p className="text-sm text-delta-muted mt-1">{error.message}</p>
          <p className="text-xs text-delta-muted mt-3">
            Verifique se o backend está rodando em http://localhost:8000
          </p>
        </div>
      )}

      {sessions && sessions.length === 0 && (
        <EmptyState
          icon={FolderOpen}
          title="Nenhuma sessão encontrada"
          description="Grave uma sessão usando o listener e depois volte aqui para análise."
        />
      )}

      {sessions && sessions.length > 0 && (
        <div className="space-y-4">
          {sessions.map((session, i) => (
            <SessionCard
              key={session.metadata.session_id}
              session={session}
              delay={i * 80}
            />
          ))}
        </div>
      )}
    </div>
  );
}
