/**
 * Loading spinner com estética racing.
 */
export default function Loading({ text = 'Carregando...' }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
      <div className="relative w-12 h-12 mb-4">
        <div className="absolute inset-0 rounded-full border-2 border-delta-border" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-delta-accent animate-spin" />
      </div>
      <p className="text-sm text-delta-muted font-mono">{text}</p>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
      {Icon && <Icon size={48} className="text-delta-border mb-4" />}
      <h3 className="font-display font-semibold text-lg text-delta-muted mb-2">
        {title}
      </h3>
      <p className="text-sm text-delta-muted/60 max-w-md text-center">
        {description}
      </p>
    </div>
  );
}
