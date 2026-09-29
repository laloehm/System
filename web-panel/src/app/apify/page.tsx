'use client';
import { useState, useEffect, useCallback } from 'react';

const NICHES = ['general', 'tenis', 'moda', 'bebes', 'mascotas'];
const DOMAIN_LABELS: Record<string, string> = {
  'MLM-SNEAKERS': 'Tenis',
  'MLM-SPORT_T_SHIRTS': 'Camisetas Dep.',
  'MLM-T_SHIRTS': 'Camisetas',
  'MLM-LEGGINGS': 'Leggings',
  'MLM-SPORT_SHORTS': 'Shorts',
  'MLM-SPORT_PANTS': 'Pantalones Dep.',
  'MLM-DRESSES_AND_SKIRTS': 'Vestidos',
  'MLM-SOCKS': 'Calcetines',
  'MLM-BACKPACKS': 'Mochilas',
  'MLM-HATS_AND_CAPS': 'Gorras',
  'MLM-TRAVEL_AND_TRAINING_BAGS': 'Bolsas',
};
const DOMAIN_TO_NICHE: Record<string, string> = {
  'MLM-SNEAKERS': 'tenis',
  'MLM-SPORT_T_SHIRTS': 'moda',
  'MLM-T_SHIRTS': 'moda',
  'MLM-LEGGINGS': 'moda',
  'MLM-SPORT_SHORTS': 'moda',
  'MLM-SPORT_PANTS': 'moda',
  'MLM-DRESSES_AND_SKIRTS': 'moda',
  'MLM-SOCKS': 'general',
  'MLM-BACKPACKS': 'general',
  'MLM-HATS_AND_CAPS': 'general',
  'MLM-TRAVEL_AND_TRAINING_BAGS': 'general',
};

interface ApifyProduct {
  SKU: string;
  articuloTitulo: string;
  nuevoPrecio: string;
  precioAnterior: string;
  precioDiscount: string;
  imgDireccion: string;
  zdireccion: string;
  Vendedor: string;
  produtoDomainID: string;
  esTiendaOficial: boolean;
  is_duplicate?: boolean;
}

export default function ApifyPage() {
  const [products, setProducts] = useState<ApifyProduct[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [filterCat, setFilterCat] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionStates, setActionStates] = useState<Record<string, 'approving' | 'linking' | 'done' | 'done_warn' | 'discarding' | 'discarded'>>({});
  const [affiliateResults, setAffiliateResults] = useState<Record<string, string>>({});
  const [selectedNiches, setSelectedNiches] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState('');

  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers = {
      ...(options?.headers || {}),
      'x-panel-key': 'gangas2026',
    };
    return fetch(path, { ...options, headers });
  };

  const loadProducts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), limit: '24' });
      if (filterCat) params.set('category', filterCat);
      const res = await apiFetch(`/api/apify/products?${params}`);
      if (res.ok) {
        const data = await res.json();
        setProducts(data.products);
        setTotal(data.total);
        setPages(data.pages);
        setCategories(data.categories);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [page, filterCat]);

  useEffect(() => { loadProducts(); }, [loadProducts]);

  const handleApprove = async (sku: string, domainId: string) => {
    const niche = selectedNiches[sku] || DOMAIN_TO_NICHE[domainId] || 'general';
    setActionStates(s => ({ ...s, [sku]: 'approving' }));
    try {
      const res = await apiFetch(`/api/apify/products/${sku}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ niche }),
      });
      if (res.ok) {
        const data = await res.json();
        const affiliateOk = data.affiliate_status === 'ok' || data.affiliate_status === 'already_affiliate';
        setActionStates(s => ({ ...s, [sku]: affiliateOk ? 'done' : 'done_warn' }));
        setAffiliateResults(r => ({ ...r, [sku]: data.affiliate_status }));
        setTimeout(() => setProducts(p => p.filter(x => x.SKU !== sku)), 2000);
      } else {
        const err = await res.json();
        alert(err.detail || 'Error al aprobar');
        setActionStates(s => { const ns = { ...s }; delete ns[sku]; return ns; });
      }
    } catch {
      alert('Error de red');
      setActionStates(s => { const ns = { ...s }; delete ns[sku]; return ns; });
    }
  };

  const handleDiscard = async (sku: string) => {
    setActionStates(s => ({ ...s, [sku]: 'discarding' }));
    try {
      const res = await apiFetch(`/api/apify/products/${sku}/discard`, { method: 'DELETE' });
      if (res.ok) {
        setActionStates(s => ({ ...s, [sku]: 'discarded' }));
        setTimeout(() => setProducts(p => p.filter(x => x.SKU !== sku)), 500);
      }
    } catch {
      setActionStates(s => { const ns = { ...s }; delete ns[sku]; return ns; });
    }
  };

  return (
    <div className="w-full overflow-x-hidden px-4 md:px-0 py-4 pb-28 space-y-4 animate-in fade-in duration-300">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[10px] font-label-caps text-primary-container tracking-widest uppercase">Apify Scraper</span>
          <h1 className="text-base font-bold text-on-surface leading-none mt-0.5">Productos Extraídos</h1>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-container rounded-lg border border-outline-variant">
          <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
          <span className="text-xs font-bold text-primary">{total}</span>
          <span className="text-[10px] text-on-surface-variant">disponibles</span>
        </div>
      </div>

      {/* Category filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <button
          onClick={() => { setFilterCat(''); setPage(1); }}
          className={`shrink-0 px-3 py-1.5 rounded-full text-[10px] font-label-caps border transition-all ${
            !filterCat ? 'bg-primary text-on-primary border-primary' : 'bg-surface-container text-on-surface-variant border-outline-variant'
          }`}
        >
          Todos
        </button>
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => { setFilterCat(cat); setPage(1); }}
            className={`shrink-0 px-3 py-1.5 rounded-full text-[10px] font-label-caps border transition-all ${
              filterCat === cat ? 'bg-primary text-on-primary border-primary' : 'bg-surface-container text-on-surface-variant border-outline-variant'
            }`}
          >
            {DOMAIN_LABELS[cat] || cat}
          </button>
        ))}
      </div>

      {/* Search Bar */}
      <div className="relative">
        <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]">search</span>
        <input
          type="text"
          placeholder="Buscar por título o SKU..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-surface-container border border-outline-variant rounded-xl py-2 pl-9 pr-4 text-sm text-on-surface outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
        />
      </div>

      {/* Products grid */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <span className="material-symbols-outlined text-4xl text-on-surface-variant animate-spin">sync</span>
          <span className="text-sm text-on-surface-variant">Cargando productos...</span>
        </div>
      ) : products.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
          <span className="material-symbols-outlined text-5xl text-on-surface-variant opacity-30">inventory_2</span>
          <p className="text-sm text-on-surface-variant">No hay productos disponibles en esta categoría.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {products
            .filter(p => 
              p.articuloTitulo.toLowerCase().includes(searchQuery.toLowerCase()) || 
              p.SKU.toLowerCase().includes(searchQuery.toLowerCase())
            )
            .map(p => {
            const state = actionStates[p.SKU];
            const suggestedNiche = selectedNiches[p.SKU] || DOMAIN_TO_NICHE[p.produtoDomainID] || 'general';
            const isDone = state === 'done' || state === 'discarded';
            return (
              <div
                key={p.SKU}
                className={`bg-surface-container-low border border-outline-variant rounded-xl overflow-hidden flex flex-col transition-all duration-300 ${
                  isDone ? 'opacity-30 scale-95 pointer-events-none' : ''
                }`}
              >
                {/* Image */}
                <div className="relative h-36 bg-white overflow-hidden">
                  {p.imgDireccion ? (
                    <img
                      src={p.imgDireccion}
                      alt={p.articuloTitulo}
                      className="absolute inset-0 w-full h-full object-contain p-2"
                    />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center bg-surface-container">
                      <span className="material-symbols-outlined text-4xl opacity-20 text-on-surface">image</span>
                    </div>
                  )}
                  {/* Category badge */}
                  <span className="absolute top-2 left-2 text-[9px] font-label-caps bg-surface-container-high/90 text-on-surface-variant px-2 py-0.5 rounded-full border border-outline-variant/50 backdrop-blur-sm">
                    {DOMAIN_LABELS[p.produtoDomainID] || p.produtoDomainID}
                  </span>
                  {p.esTiendaOficial && (
                    <span className="absolute top-2 right-2 text-[9px] font-label-caps bg-primary/20 text-primary px-2 py-0.5 rounded-full border border-primary/20 backdrop-blur-sm">
                      Oficial
                    </span>
                  )}
                  {p.is_duplicate && (
                    <span className="absolute bottom-2 left-2 right-2 text-[10px] font-label-caps bg-error text-on-error px-2 py-1 rounded-md text-center border border-error/50 shadow-lg animate-pulse">
                      YA PUBLICADO
                    </span>
                  )}
                </div>

                {/* Info */}
                <div className="p-3 flex flex-col gap-2 flex-1">
                  <p className="text-xs font-medium text-on-surface leading-snug line-clamp-2">{p.articuloTitulo}</p>
                  
                  <div className="flex items-center gap-2">
                    <span className="text-primary font-bold text-sm">${p.nuevoPrecio}</span>
                    {p.precioAnterior && (
                      <span className="text-on-surface-variant line-through text-xs">${p.precioAnterior}</span>
                    )}
                    {p.precioDiscount && (
                      <span className="text-[10px] font-bold text-error bg-error/10 px-1.5 py-0.5 rounded border border-error/20 ml-auto">
                        {p.precioDiscount}
                      </span>
                    )}
                  </div>

                  {p.Vendedor && (
                    <span className="text-[9px] text-on-surface-variant font-label-caps">{p.Vendedor}</span>
                  )}

                  {/* Niche selector */}
                  <select
                    value={suggestedNiche}
                    onChange={e => setSelectedNiches(s => ({ ...s, [p.SKU]: e.target.value }))}
                    className="w-full bg-surface-container border border-outline-variant/50 rounded-lg p-1.5 text-[10px] text-on-surface-variant outline-none focus:border-primary transition-colors"
                  >
                    {NICHES.map(n => (
                      <option key={n} value={n}>{n.charAt(0).toUpperCase() + n.slice(1)}</option>
                    ))}
                  </select>

                  {/* Actions */}
                  <div className="flex gap-2 mt-auto pt-1">
                    <a
                      href={p.zdireccion}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center px-3 py-2 bg-surface-container border border-outline-variant rounded-lg text-[10px] text-on-surface-variant hover:text-primary hover:bg-primary/5 transition-all"
                      title="Ver en tienda"
                    >
                      <span className="material-symbols-outlined text-[14px]">open_in_new</span>
                    </a>
                    <button
                      onClick={() => handleDiscard(p.SKU)}
                      disabled={!!state}
                      className="flex-1 flex items-center justify-center gap-1 py-2 bg-surface-container border border-outline-variant rounded-lg text-[10px] font-label-caps text-error hover:bg-error/10 active:scale-95 transition-all disabled:opacity-40"
                    >
                      <span className="material-symbols-outlined text-[14px]">
                        {state === 'discarding' ? 'sync' : 'delete'}
                      </span>
                      {state === 'discarding' ? 'Descartando...' : 'Descartar'}
                    </button>
                    <button
                      onClick={() => handleApprove(p.SKU, p.produtoDomainID)}
                      disabled={!!state}
                      className={`flex-[2] flex items-center justify-center gap-1 py-2 rounded-lg text-[10px] font-bold active:scale-95 transition-all disabled:opacity-40 ${
                        state === 'done' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                        state === 'done_warn' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                        'bg-primary-container text-on-primary-container hover:brightness-110'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[14px]">
                        {state === 'approving' ? 'sync' :
                         state === 'done' ? 'check_circle' :
                         state === 'done_warn' ? 'warning' :
                         'add_shopping_cart'}
                      </span>
                      {state === 'approving' ? 'Generando link...' :
                       state === 'done' ? '¡Link listo!' :
                       state === 'done_warn' ? 'En cola (sin link)' :
                       'Aprobar + Afiliar'}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-4">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 text-xs font-label-caps bg-surface-container border border-outline-variant rounded-lg text-on-surface disabled:opacity-30 active:scale-95 transition-all"
          >
            ← Anterior
          </button>
          <span className="text-xs text-on-surface-variant font-label-caps">{page} / {pages}</span>
          <button
            onClick={() => setPage(p => Math.min(pages, p + 1))}
            disabled={page === pages}
            className="px-4 py-2 text-xs font-label-caps bg-surface-container border border-outline-variant rounded-lg text-on-surface disabled:opacity-30 active:scale-95 transition-all"
          >
            Siguiente →
          </button>
        </div>
      )}
    </div>
  );
}
