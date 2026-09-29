'use client';
import { useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      if (res.ok) {
        const next = searchParams.get('next') || '/';
        router.replace(next);
        router.refresh();
      } else {
        setError('Clave de acceso incorrecta.');
      }
    } catch {
      setError('Error de conexión con el servidor.');
    }
    setLoading(false);
  };

  return (
    <div className="w-full max-w-lg mx-auto p-4 md:p-6 my-auto">
      <div className="bg-surface-container p-8 md:p-10 rounded-3xl border border-outline-variant/30 shadow-2xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-16 h-16 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mx-auto mb-2 shadow-inner">
            <span className="material-symbols-outlined text-4xl">lock</span>
          </div>
          <h1 className="text-2xl font-bold text-on-surface">Gangas MX</h1>
          <p className="text-sm text-on-surface-variant">
            Ingresa tu clave para entrar al Panel de Administración
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block">
              Clave de Acceso
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                autoFocus
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="gangas2026"
                className="w-full pl-4 pr-12 py-4 rounded-xl border border-outline-variant/40 bg-surface text-on-surface text-base placeholder:text-on-surface-variant/30 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono shadow-inner"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-on-surface-variant/60 hover:text-on-surface p-1 transition-colors"
                title={showKey ? "Ocultar clave" : "Mostrar clave"}
              >
                <span className="material-symbols-outlined text-2xl">
                  {showKey ? 'visibility_off' : 'visibility'}
                </span>
              </button>
            </div>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-error/10 border border-error/20 text-xs text-error font-semibold flex items-center gap-2">
              <span className="material-symbols-outlined text-base shrink-0">error</span>
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !key.trim()}
            className="w-full py-4 bg-primary text-on-primary hover:brightness-110 active:scale-[0.99] rounded-xl font-bold text-base disabled:opacity-50 transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer"
          >
            {loading ? 'Verificando...' : 'Entrar al Panel'}
          </button>
        </form>

        <div className="pt-2 text-center text-xs text-on-surface-variant/70">
          Clave habilitada: <code className="bg-surface-container-high px-2 py-1 rounded text-on-surface font-mono font-bold">gangas2026</code>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="w-full max-w-lg p-8 rounded-3xl bg-surface-container border border-outline-variant/30 text-center space-y-4 mx-auto my-auto">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto"></div>
        <p className="text-sm font-semibold text-on-surface">Cargando...</p>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
