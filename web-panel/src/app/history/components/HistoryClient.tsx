'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

export default function HistoryClient() {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('');

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await apiFetch('/api/history');
        if (res.ok) {
          const data = await res.json();
          setHistory(data.history || []);
        } else {
          setError('No se pudo cargar el historial.');
        }
      } catch (e) {
        setError('Error de conexión.');
      }
      setLoading(false);
    };
    fetchHistory();
  }, []);

  const handleAction = async (id: string, actionType: string, network?: string) => {
    setActionLoading(`${id}-${actionType}-${network}`);
    try {
      let url = '';
      let method = 'POST';
      
      if (actionType === 'republish') {
        url = `/api/history/${id}/republish/${network}`;
      } else if (actionType === 'video') {
        url = `/api/history/${id}/video`;
      } else if (actionType === 'delete') {
        url = `/api/history/${id}`;
        method = 'DELETE';
      }

      const res = await apiFetch(url, { method });
      if (res.ok) {
        if (actionType === 'delete') {
          setHistory(prev => prev.filter(p => p.id !== id));
        }
        alert('Acción completada con éxito.');
      } else {
        alert('Error al ejecutar la acción.');
      }
    } catch (e) {
      alert('Error de red al ejecutar la acción.');
    }
    setActionLoading(null);
  };

  return (
    <div className="w-full">
      {/* Mobile Back Button (Optional context) */}
      <div className="md:hidden flex items-center gap-3 mb-6">
        <Link href="/queues" className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface">
          <span className="material-symbols-outlined block">arrow_back</span>
        </Link>
        <h1 className="text-xl font-bold text-primary">Historial</h1>
      </div>

      {/* Header Section */}
      <div className="bg-surface-container p-6 rounded-xl mb-6 border-l-4 border-l-primary-container shadow-sm border-t border-r border-b border-outline-variant/30">
        <div className="flex items-center gap-3 mb-2">
          <span className="material-symbols-outlined text-primary-container text-2xl">history</span>
          <h2 className="font-headline-md text-xl text-on-surface truncate">Panel de Administración Web</h2>
        </div>
        <p className="font-body-sm text-on-surface-variant">
          Mostrando los últimos {history.length} productos publicados por el bot.
        </p>
      </div>

      {loading ? (
        <div className="text-center p-10 flex flex-col items-center">
          <span className="material-symbols-outlined animate-spin text-primary-container text-4xl mb-4">progress_activity</span>
          <p className="text-on-surface-variant font-label-caps uppercase tracking-widest">Cargando Historial...</p>
        </div>
      ) : error ? (
        <div className="bg-error/10 border border-error/30 rounded-xl p-4 flex items-center gap-3">
          <span className="material-symbols-outlined text-error">error</span>
          <p className="text-sm font-body-sm text-error">{error}</p>
        </div>
      ) : history.length === 0 ? (
        <div className="p-12 border border-dashed border-outline-variant rounded-xl text-center flex flex-col items-center">
          <span className="material-symbols-outlined text-on-surface-variant text-5xl mb-4">history_toggle_off</span>
          <p className="font-body-lg text-on-surface-variant">No hay productos publicados aún.</p>
        </div>
      ) : (
        <>
          {/* Action Buttons (Search & Filter) */}
          <div className="mb-6 flex flex-col md:flex-row gap-4">
            <div className="flex-1 flex items-center gap-3 p-2 bg-surface-container border border-outline-variant rounded-lg text-on-surface-variant transition-colors">
              <span className="material-symbols-outlined text-primary-container ml-2">search</span>
              <input 
                type="text" 
                placeholder="Buscar por nombre..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent border-none outline-none flex-1 text-on-surface placeholder:text-on-surface-variant/50 font-body-sm w-full"
              />
            </div>
            <div className="flex items-center gap-3 p-2 bg-surface-container border border-outline-variant rounded-lg text-on-surface-variant transition-colors md:w-64">
              <span className="material-symbols-outlined text-primary-container ml-2">calendar_today</span>
              <input 
                type="date" 
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
                className="bg-transparent border-none outline-none flex-1 text-on-surface font-body-sm w-full"
              />
              {dateFilter && (
                <button onClick={() => setDateFilter('')} className="material-symbols-outlined text-on-surface-variant hover:text-error mr-1">
                  close
                </button>
              )}
            </div>
          </div>

          {/* Product Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {history
              .filter(p => {
                const matchesSearch = (p.title || '').toLowerCase().includes(searchQuery.toLowerCase());
                if (!dateFilter) return matchesSearch;
                
                if (!p.published_at) return false; // Si no tiene fecha y hay filtro, no lo mostramos
                const pubDate = new Date(p.published_at);
                // Ajustamos a zona horaria local para comparar con el input YYYY-MM-DD
                const formattedPubDate = pubDate.toLocaleDateString('en-CA'); // 'YYYY-MM-DD' en local
                return matchesSearch && formattedPubDate === dateFilter;
              })
              .map((p, idx) => {
              const isExpanded = expandedId === p.id;
              return (
              <div 
                key={idx} 
                className="w-full flex flex-col bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant rounded-lg text-left group transition-all cursor-pointer"
                onClick={() => setExpandedId(isExpanded ? null : p.id)}
              >
                <div className="flex items-center p-3">
                  {/* Minatura (Image) */}
                  <div className="w-14 h-14 bg-white rounded-md shrink-0 overflow-hidden flex items-center justify-center p-1 mr-4 border border-outline-variant/50">
                    <img 
                      src={p.image_url || p.images?.[0] || 'https://via.placeholder.com/150'} 
                      alt="Product" 
                      className="w-full h-full object-contain mix-blend-multiply"
                      onError={(e) => { (e.target as HTMLImageElement).src = 'https://via.placeholder.com/150'; }}
                    />
                  </div>

                  {/* Info Text */}
                  <div className="flex-1 min-w-0 pr-4">
                    <h3 className="text-on-surface truncate font-body-sm font-bold mb-1">
                      {p.title || 'Producto sin título'}
                    </h3>
                    <div className="flex items-center gap-2">
                      <span className="text-primary-container font-label-caps text-[10px] font-bold tracking-wider">{p.offer_price || p.price || '$?'}</span>
                      <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
                      <span className="text-on-surface-variant font-label-caps text-[10px] uppercase tracking-wider capitalize">{p.niche || 'General'}</span>
                      {p.published_at && (
                        <>
                          <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
                          <span className="text-on-surface-variant font-label-caps text-[10px] uppercase tracking-wider">
                            {new Date(p.published_at).toLocaleDateString('es-MX', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* External Link Action */}
                  <a 
                    href={p.url || p.affiliate_url || '#'} 
                    target="_blank" 
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="p-2.5 rounded-full bg-surface-container hover:bg-primary/20 text-on-surface-variant group-hover:text-primary transition-all active:scale-90 shadow-sm border border-outline-variant/30"
                    title="Abrir publicación original"
                  >
                    <span className="material-symbols-outlined text-[20px]">open_in_new</span>
                  </a>
                </div>

                {/* Action Buttons Panel */}
                {isExpanded && (
                  <div className="border-t border-outline-variant p-3 bg-surface-container/50 grid grid-cols-2 md:grid-cols-4 gap-2" onClick={e => e.stopPropagation()}>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'telegram')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-primary mb-1 text-lg">send</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">Telegram</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'facebook')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-[#1877F2] mb-1 text-lg">groups</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">FB Grupos</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'fb_page')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-[#1877F2] mb-1 text-lg">pages</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">FB Página</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'pinterest')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-[#E60023] mb-1 text-lg">push_pin</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">Pinterest</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'web')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-[#0F9D58] mb-1 text-lg">public</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">Web</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'video')}
                      disabled={!!actionLoading}
                      className="flex flex-col items-center justify-center py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant rounded-md transition-colors"
                    >
                      <span className="material-symbols-outlined text-[#FF0000] mb-1 text-lg">movie</span>
                      <span className="font-label-caps text-[9px] uppercase tracking-wider">Video</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'republish', 'all')}
                      disabled={!!actionLoading}
                      className="col-span-2 flex items-center justify-center gap-2 py-2 px-1 bg-surface-container hover:bg-primary/10 border border-outline-variant text-on-surface rounded-md transition-colors mt-1"
                    >
                      <span className="material-symbols-outlined text-lg text-primary">sync</span>
                      <span className="font-label-caps text-[10px] uppercase tracking-wider font-bold">Volver a Publicar (Todo)</span>
                    </button>
                    <button 
                      onClick={() => handleAction(p.id, 'delete')}
                      disabled={!!actionLoading}
                      className="col-span-2 md:col-span-4 flex items-center justify-center gap-2 py-2 px-1 bg-error/10 hover:bg-error/20 border border-error/30 text-error rounded-md transition-colors mt-1"
                    >
                      <span className="material-symbols-outlined text-lg">delete</span>
                      <span className="font-label-caps text-[10px] uppercase tracking-wider font-bold">Eliminar del Historial</span>
                    </button>
                  </div>
                )}
              </div>
            )})}
          </div>

          {/* Pagination */}
          <button className="w-full flex items-center justify-center gap-3 p-4 mt-6 bg-secondary-container hover:bg-surface-container-highest border border-outline-variant rounded-lg text-on-surface transition-all active:scale-95 duration-100 group">
            <span className="font-label-caps text-xs uppercase tracking-widest">SIGUIENTE PÁGINA</span>
            <span className="material-symbols-outlined text-primary-container group-hover:translate-x-1 transition-transform">chevron_right</span>
          </button>
        </>
      )}
    </div>
  );
}
