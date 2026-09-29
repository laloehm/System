'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

interface DiscardedProduct {
  id: string;
  title: string;
  reason: string;
  details: Record<string, any>;
  url: string;
  offer_price: string;
  list_price: string;
  discount: string;
  timestamp: string;
  scraper_source: string;
}

interface DiscardedResponse {
  total: number;
  discarded: DiscardedProduct[];
  summary: Record<string, number>;
  limit: number;
  offset: number;
}

export default function DiscardedClient() {
  const [discarded, setDiscarded] = useState<DiscardedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedReason, setSelectedReason] = useState('');
  const [days, setDays] = useState(7);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [limit] = useState(50);
  const [clearingOld, setClearingOld] = useState(false);

  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    const fetchDiscarded = async () => {
      try {
        setLoading(true);
        const offset = (page - 1) * limit;
        let url = `/api/discarded?limit=${limit}&offset=${offset}&days=${days}`;
        if (selectedReason) {
          url += `&reason=${encodeURIComponent(selectedReason)}`;
        }

        const res = await apiFetch(url);
        if (res.ok) {
          const data: DiscardedResponse = await res.json();
          setDiscarded(data.discarded || []);
          setSummary(data.summary || {});
          setTotal(data.total);
        } else {
          setError('No se pudo cargar los productos descartados.');
        }
      } catch (e) {
        setError('Error de conexión.');
      }
      setLoading(false);
    };

    fetchDiscarded();
  }, [page, limit, days, selectedReason]);

  const handleClearOld = async () => {
    if (!confirm(`Eliminar todos los descartados más antiguos de ${days} días?`)) return;

    setClearingOld(true);
    try {
      const res = await apiFetch('/api/discarded/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days }),
      });

      if (res.ok) {
        alert('Registros antiguos eliminados exitosamente.');
        setPage(1);
        const url = `/api/discarded?limit=${limit}&offset=0&days=${days}`;
        const reloadRes = await apiFetch(url);
        if (reloadRes.ok) {
          const data: DiscardedResponse = await reloadRes.json();
          setDiscarded(data.discarded || []);
          setSummary(data.summary || {});
          setTotal(data.total);
        }
      } else {
        alert('Error al eliminar registros.');
      }
    } catch (e) {
      alert('Error de red.');
    }
    setClearingOld(false);
  };

  const handleDeleteSingle = async (id: string, timestamp?: string) => {
    if (!confirm('¿Eliminar este registro de descartados?')) return;
    try {
      const url = timestamp
        ? `/api/discarded/${id}?timestamp=${encodeURIComponent(timestamp)}`
        : `/api/discarded/${id}`;
      const res = await apiFetch(url, { method: 'DELETE' });
      if (res.ok) {
        setDiscarded(prev => prev.filter(p => !(p.id === id && (timestamp ? p.timestamp === timestamp : true))));
        setTotal(prev => Math.max(0, prev - 1));
      } else {
        alert('Error al eliminar registro.');
      }
    } catch (e) {
      alert('Error de conexión.');
    }
  };

  const handleClearAll = async () => {
    if (!confirm('🚨 ATENCIÓN 🚨\n\n¿Estás seguro de que deseas VACIAR TODO el historial de descartados?')) return;
    try {
      const res = await apiFetch('/api/discarded/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all: true }),
      });
      if (res.ok) {
        setDiscarded([]);
        setSummary({});
        setTotal(0);
        alert('Historial de descartados vaciado por completo.');
      } else {
        alert('Error al vaciar descartados.');
      }
    } catch (e) {
      alert('Error de conexión.');
    }
  };

  const handleRescue = async (id: string, niche: string = 'general', timestamp?: string) => {
    if (!confirm(`¿Rescatar este producto e insertarlo en la cola de ${niche.toUpperCase()}?`)) return;
    try {
      const res = await apiFetch(`/api/discarded/${id}/rescue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ niche, timestamp }),
      });
      if (res.ok) {
        setDiscarded(prev => prev.filter(p => !(p.id === id && (timestamp ? p.timestamp === timestamp : true))));
        setTotal(prev => Math.max(0, prev - 1));
        alert(`Producto rescatado y movido a la cola de ${niche.toUpperCase()}.`);
      } else {
        alert('Error al rescatar el producto.');
      }
    } catch (e) {
      alert('Error de conexión.');
    }
  };

  const formatDate = (isoString: string) => {
    try {
      return new Date(isoString).toLocaleString('es-MX');
    } catch {
      return isoString;
    }
  };

  const formatPrice = (price: string) => {
    if (!price) return '-';
    try {
      const numStr = price.replace(/[^0-9.-]/g, '');
      const num = parseFloat(numStr);
      return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(num);
    } catch {
      return price;
    }
  };

  const reasonColors: Record<string, string> = {
    'Blacklist': 'bg-red-100 text-red-800',
    'Discount': 'bg-yellow-100 text-yellow-800',
    'Price': 'bg-orange-100 text-orange-800',
    'Savings': 'bg-pink-100 text-pink-800',
    'Already': 'bg-gray-100 text-gray-800',
    'Excluded': 'bg-purple-100 text-purple-800',
    'No matched': 'bg-blue-100 text-blue-800',
  };

  const getReasonColor = (reason: string | undefined): string => {
    if (!reason) return 'bg-gray-100 text-gray-800';
    for (const [key, color] of Object.entries(reasonColors)) {
      if (reason.includes(key)) return color;
    }
    return 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="w-full">
      {/* Mobile Back Button */}
      <div className="md:hidden flex items-center gap-3 mb-6">
        <Link
          href="/queues"
          className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface"
        >
          <span className="material-symbols-outlined block">arrow_back</span>
        </Link>
        <h1 className="text-xl font-bold text-primary">Descartados</h1>
      </div>

      {/* Header Section */}
      <div className="bg-surface-container p-6 rounded-xl mb-6 border-l-4 border-l-primary-container shadow-sm border-t border-r border-b border-outline-variant/30">
        <div className="flex items-center gap-3 mb-2">
          <span className="material-symbols-outlined text-primary-container text-2xl">
            delete_outline
          </span>
          <h2 className="font-headline-md text-xl text-on-surface truncate">
            Panel de Productos Descartados
          </h2>
        </div>
        <p className="font-body-sm text-on-surface-variant">
          {loading ? 'Cargando...' : `Total de ${total} productos descartados en los últimos ${days} días`}
        </p>
      </div>

      {/* Filters and Summary */}
      {!loading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {/* Days Filter */}
          <div className="bg-surface-container p-4 rounded-lg border border-outline-variant/30">
            <label className="text-sm font-semibold text-on-surface-variant mb-2 block">
              Período (días)
            </label>
            <select
              value={days}
              onChange={(e) => {
                setDays(parseInt(e.target.value));
                setPage(1);
              }}
              className="w-full p-2 rounded border border-outline-variant bg-surface text-on-surface"
            >
              <option value={1}>Últimas 24h</option>
              <option value={7}>Últimos 7 días</option>
              <option value={30}>Últimos 30 días</option>
              <option value={90}>Últimos 90 días</option>
              <option value={0}>Todos</option>
            </select>
          </div>

          {/* Reason Filter */}
          <div className="bg-surface-container p-4 rounded-lg border border-outline-variant/30">
            <label className="text-sm font-semibold text-on-surface-variant mb-2 block">
              Razón de Descarte
            </label>
            <select
              value={selectedReason}
              onChange={(e) => {
                setSelectedReason(e.target.value);
                setPage(1);
              }}
              className="w-full p-2 rounded border border-outline-variant bg-surface text-on-surface"
            >
              <option value="">Todas las razones</option>
              {Object.keys(summary).map((reason, idx) => (
                <option key={`opt-${reason}-${idx}`} value={reason}>
                  {reason} ({summary[reason]})
                </option>
              ))}
            </select>
          </div>

          {/* Clear Actions */}
          <div className="bg-surface-container p-4 rounded-lg border border-outline-variant/30 flex flex-col sm:flex-row gap-2 justify-end">
            <button
              onClick={handleClearOld}
              disabled={clearingOld}
              className="flex-1 px-4 py-2 bg-error/20 text-error border border-error/30 rounded hover:bg-error/30 disabled:opacity-50 text-xs font-semibold"
            >
              {clearingOld ? 'Eliminando...' : `Limpiar > ${days}d`}
            </button>
            <button
              onClick={handleClearAll}
              className="flex-1 px-4 py-2 bg-error text-on-error rounded hover:bg-error/80 text-xs font-semibold"
            >
              Vaciar Todo
            </button>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      {!loading && Object.keys(summary).length > 0 && (
        <div className="bg-surface-container p-4 rounded-lg border border-outline-variant/30 mb-6">
          <h3 className="font-semibold text-on-surface mb-3">Resumen por Razón</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(summary)
              .sort((a, b) => b[1] - a[1])
              .map(([reason, count], idx) => (
                <div
                  key={`sum-${reason || 'unknown'}-${idx}`}
                  className={`p-3 rounded text-center cursor-pointer hover:opacity-80 ${getReasonColor(reason)}`}
                  onClick={() => {
                    setSelectedReason(reason || '');
                    setPage(1);
                  }}
                >
                  <div className="text-sm font-semibold truncate">{reason || 'Unknown'}</div>
                  <div className="text-lg font-bold">{count}</div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="text-center p-10 flex flex-col items-center">
          <span className="material-symbols-outlined animate-spin text-primary-container text-4xl mb-4">
            progress_activity
          </span>
          <p className="text-on-surface-variant font-label-caps uppercase tracking-widest">
            Cargando Descartados...
          </p>
        </div>
      ) : error ? (
        <div className="text-center p-10 flex flex-col items-center bg-error-container rounded-lg">
          <span className="material-symbols-outlined text-error text-4xl mb-4">error</span>
          <p className="text-on-error-container font-label-caps">{error}</p>
        </div>
      ) : discarded.length === 0 ? (
        <div className="text-center p-10 flex flex-col items-center bg-surface-container rounded-lg">
          <span className="material-symbols-outlined text-primary-container text-4xl mb-4">
            check_circle
          </span>
          <p className="text-on-surface-variant font-label-caps">
            No hay productos descartados con estos filtros
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {discarded.map((product, idx) => (
            <div
              key={`${product.id}-${product.timestamp || ''}-${idx}`}
              className="bg-surface-container rounded-lg border border-outline-variant/30 overflow-hidden hover:shadow-md transition-shadow"
            >
              <div
                className="p-4 cursor-pointer hover:bg-surface-container-high transition-colors"
                onClick={() =>
                  setExpandedId(expandedId === product.id ? null : product.id)
                }
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-on-surface truncate">
                      {product.title}
                    </h3>
                    <p className="text-sm text-on-surface-variant mt-1">
                      ID: {product.id}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getReasonColor(product.reason)}`}>
                      {product.reason || 'Unknown'}
                    </span>
                    <span className="material-symbols-outlined transition-transform">
                      {expandedId === product.id ? 'expand_less' : 'expand_more'}
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-4 mt-3 text-sm">
                  {product.offer_price && (
                    <div>
                      <span className="text-on-surface-variant">Oferta: </span>
                      <span className="font-semibold text-on-surface">
                        {formatPrice(product.offer_price)}
                      </span>
                    </div>
                  )}
                  {product.list_price && (
                    <div>
                      <span className="text-on-surface-variant">Original: </span>
                      <span className="font-semibold text-on-surface line-through">
                        {formatPrice(product.list_price)}
                      </span>
                    </div>
                  )}
                  {product.discount && (
                    <div>
                      <span className="text-on-surface-variant">Descuento: </span>
                      <span className="font-semibold text-on-surface">{product.discount}</span>
                    </div>
                  )}
                  <div className="ml-auto">
                    <span className="text-xs text-on-surface-variant">
                      {formatDate(product.timestamp)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === product.id && (
                <div className="bg-surface-bright p-4 border-t border-outline-variant/30 space-y-3">
                  <div>
                    <p className="text-xs text-on-surface-variant font-semibold mb-1">URL</p>
                    {product.url ? (
                      <a
                        href={product.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline text-sm break-all"
                      >
                        {product.url}
                      </a>
                    ) : (
                      <p className="text-sm text-on-surface-variant">-</p>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-on-surface-variant font-semibold mb-1">
                        Fuente
                      </p>
                      <p className="text-sm bg-surface rounded px-2 py-1">
                        {product.scraper_source}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-on-surface-variant font-semibold mb-1">
                        Fecha Descarte
                      </p>
                      <p className="text-sm bg-surface rounded px-2 py-1">
                        {formatDate(product.timestamp)}
                      </p>
                    </div>
                  </div>

                  {product.details && Object.keys(product.details).length > 0 && (
                    <div>
                      <p className="text-xs text-on-surface-variant font-semibold mb-2">
                        Detalles Técnicos
                      </p>
                      <div className="bg-surface rounded p-2 text-xs space-y-1">
                        {Object.entries(product.details).map(([key, value], dIdx) => (
                          <div key={`det-${key}-${dIdx}`} className="flex justify-between">
                            <span className="text-on-surface-variant">{key}:</span>
                            <span className="text-on-surface font-mono">
                              {JSON.stringify(value)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Buttons: Rescue & Delete */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-outline-variant/20">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-on-surface-variant font-semibold">Rescatar a:</span>
                      <select
                        className="bg-surface text-xs text-on-surface rounded p-1.5 border border-outline-variant outline-none"
                        defaultValue="general"
                        id={`rescue_select_${product.id}_${idx}`}
                      >
                        <option value="general">General</option>
                        <option value="baby">Bebés</option>
                        <option value="pets">Mascotas</option>
                        <option value="tenis">Tenis</option>
                        <option value="moda">Moda</option>
                      </select>
                      <button
                        onClick={() => {
                          const select = document.getElementById(`rescue_select_${product.id}_${idx}`) as HTMLSelectElement;
                          const niche = select ? select.value : 'general';
                          handleRescue(product.id, niche, product.timestamp);
                        }}
                        className="px-3 py-1.5 bg-primary text-on-primary rounded text-xs font-semibold hover:bg-primary/90 flex items-center gap-1 shadow-sm"
                      >
                        <span className="material-symbols-outlined text-[16px]">autorenew</span>
                        Rescatar a Cola
                      </button>
                    </div>

                    <button
                      onClick={() => handleDeleteSingle(product.id, product.timestamp)}
                      className="px-3 py-1.5 bg-error/20 text-error border border-error/30 rounded text-xs font-semibold hover:bg-error/30 flex items-center gap-1"
                    >
                      <span className="material-symbols-outlined text-[16px]">delete</span>
                      Eliminar Registro
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {!loading && total > limit && (
        <div className="mt-6 flex items-center justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded bg-primary text-on-primary hover:bg-primary/80 disabled:opacity-50"
          >
            Anterior
          </button>
          <span className="text-on-surface-variant">
            Página {page} de {Math.ceil(total / limit)}
          </span>
          <button
            onClick={() => setPage(Math.min(Math.ceil(total / limit), page + 1))}
            disabled={page >= Math.ceil(total / limit)}
            className="px-4 py-2 rounded bg-primary text-on-primary hover:bg-primary/80 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
