'use client';
import { useState } from 'react';
import Link from 'next/link';

export default function QueueClient({ 
  niche, 
  initialProducts 
}: { 
  niche: string, 
  initialProducts: any[] 
}) {
  const [products, setProducts] = useState<any[]>(initialProducts);
  const [editingProduct, setEditingProduct] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [isRefilling, setIsRefilling] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [sortBy, setSortBy] = useState<'default' | 'savings_desc' | 'discount_desc' | 'price_asc'>('default');
  const [isSortingQueue, setIsSortingQueue] = useState(false);
  const [isGeneratingAffiliates, setIsGeneratingAffiliates] = useState(false);

  const getProductSavings = (p: any): number => {
    try {
      const parsePrice = (str: any) => {
        if (!str) return 0;
        let s = String(str).replace(/\$/g, '').trim();
        if (/,\d{1,2}$/.test(s)) s = s.replace(/,(\d{1,2})$/, '.$1');
        s = s.replace(/,/g, '').replace(/[^0-9.]/g, '');
        return parseFloat(s) || 0;
      };
      const list = parsePrice(p.list_price || p.original_price);
      const offer = parsePrice(p.offer_price || p.price);
      return (list > offer && list > 0) ? (list - offer) : 0;
    } catch {
      return 0;
    }
  };

  const getProductDiscount = (p: any): number => {
    try {
      const d = String(p.discount || '0');
      const m = d.match(/(\d+)/);
      return m ? parseInt(m[1], 10) : 0;
    } catch {
      return 0;
    }
  };

  const handleSortQueueBySavings = async () => {
    if (!confirm(`¿Reordenar físicamente la cola de ${niche.toUpperCase()} por mayor ahorro real en pesos ($ MXN)?\n\nEl bot publicará primero las ofertas con mayor beneficio para los usuarios.`)) {
      return;
    }
    setIsSortingQueue(true);
    try {
      const res = await apiFetch(`/api/queues/${niche}/sort-by-savings`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (data.products && Array.isArray(data.products)) {
          setProducts(data.products);
        } else {
          await loadData();
        }
        setSortBy('default');
        alert(`✅ Cola reordenada: ${data.count || products.length} productos organizados de mayor a menor ahorro en pesos.`);
      } else {
        alert("Error al reordenar la cola en el servidor.");
      }
    } catch (e) {
      console.error(e);
      alert("Error de conexión al reordenar la cola.");
    } finally {
      setIsSortingQueue(false);
    }
  };

  const displayedProducts = products
    .filter(p => 
      (p.title || '').toLowerCase().includes(searchQuery.toLowerCase()) || 
      (p.id || '').toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => {
      if (sortBy === 'savings_desc') {
        return getProductSavings(b) - getProductSavings(a);
      }
      if (sortBy === 'discount_desc') {
        return getProductDiscount(b) - getProductDiscount(a);
      }
      if (sortBy === 'price_asc') {
        const parsePrice = (str: any) => {
          if (!str) return 0;
          let s = String(str).replace(/\$/g, '').trim();
          if (/,\d{1,2}$/.test(s)) s = s.replace(/,(\d{1,2})$/, '.$1');
          s = s.replace(/,/g, '').replace(/[^0-9.]/g, '');
          return parseFloat(s) || 0;
        };
        return parsePrice(a.offer_price || a.price) - parsePrice(b.offer_price || b.price);
      }
      return 0;
    });

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  const loadData = async () => {
    try {
      const res = await apiFetch(`/api/queues/${niche}`, { cache: 'no-store' });
      if (res.ok) {
        const d = await res.json();
        setProducts(d.products || []);
      }
    } catch(e) {
      console.error("Ambos fetch fallaron", e);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!file || !editingProduct) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await apiFetch('/api/upload_image', {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setEditingProduct({
          ...editingProduct, 
          visual_capture: data.path,
          screenshot: data.path,
          image_url: ''
        });
      } else {
        alert("Error al subir la imagen.");
      }
    } catch (e) {
      console.error(e);
      alert("Error de red al subir la imagen.");
    } finally {
      setIsUploading(false);
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    if (e.clipboardData.files && e.clipboardData.files.length > 0) {
      handleFileUpload(e.clipboardData.files[0]);
    }
  };

  const handleSave = async () => {
    if (!editingProduct) return;
    if (isUploading) {
      alert("Espera a que termine de subir la imagen antes de guardar.");
      return;
    }
    setSaving(true);
    
    // Auto-formatear precios y descuentos
    const formattedProduct = { ...editingProduct };
    
    const formatPrice = (v: string | undefined) => {
      if (!v) return v;
      let t = v.trim();
      if (t.toLowerCase() === 'revisar' || t === 'N/A' || t.toLowerCase() === 'gratis') return t;
      if (/^\d/.test(t)) return `$${t}`;
      return t;
    };
    
    const formatDiscount = (v: string | undefined) => {
      if (!v) return v;
      let t = v.trim();
      const m = t.match(/^-?(\d+)\s*(%?)(\s*off)?$/i);
      if (m) return `${m[1]}% OFF`;
      return t;
    };

    formattedProduct.original_price = formatPrice(formattedProduct.original_price);
    formattedProduct.list_price = formatPrice(formattedProduct.list_price || formattedProduct.original_price);
    formattedProduct.offer_price = formatPrice(formattedProduct.offer_price);
    formattedProduct.discount = formatDiscount(formattedProduct.discount);

    try {
      const isNew = !formattedProduct.id;
      const url = isNew 
        ? `/api/queues/${niche}` 
        : `/api/queues/${niche}/${formattedProduct.id}`;
      
      const res = await apiFetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formattedProduct),
      });
      
      if (res.ok) {
        setEditingProduct(null);
        loadData();
      }
    } catch (e) {
      console.error("Save failed", e);
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('¿Seguro que deseas eliminar este producto?')) return;
    try {
      await apiFetch(`/api/queues/${niche}/${id}`, { method: 'DELETE' });
      loadData();
    } catch (e) {
      console.error("Delete failed", e);
    }
  };

  const handleClearQueue = async () => {
    if (!confirm('🚨 ATENCIÓN 🚨\n\n¿Estás SEGURO de que deseas vaciar toda la cola? Esto no se puede deshacer.')) return;
    try {
      const res = await apiFetch(`/api/bot/clear/${niche}`, { method: 'POST' });
      if (res.ok) {
        setProducts([]);
        alert('Cola vaciada con éxito.');
      }
    } catch (e) {
      console.error(e);
      alert('Error al vaciar cola.');
    }
  };

  const handleRefillQueue = async () => {
    setIsRefilling(true);
    try {
      const res = await apiFetch(`/api/bot/refill`, { method: 'POST' });
      if (res.ok) {
        alert('Proceso de auto-llenado iniciado en el servidor. Esto puede tomar varios minutos. Los productos aparecerán gradualmente.');
      } else {
        alert('Error al iniciar el llenado.');
      }
    } catch (e) {
      console.error(e);
      alert('Error de conexión.');
    }
    setIsRefilling(false);
  };

  const handleGenerateAffiliates = async () => {
    setIsGeneratingAffiliates(true);
    try {
      const res = await apiFetch(`/api/queues/${niche}/generate-all-affiliates`, { method: 'POST' });
      if (res.ok) {
        alert('🚀 Generación masiva de enlaces meli.la iniciada en el servidor (Linux) con tu sesión activa.\n\nEsto toma de 1 a 2 minutos. En breve los productos aparecerán con su link listo y sin la alerta roja.');
      } else {
        alert('Error al iniciar la generación de enlaces.');
      }
    } catch (e) {
      console.error(e);
      alert('Error de conexión.');
    }
    setIsGeneratingAffiliates(false);
  };

  const resolveImage = (p: any) => {
    const img = p.image_url || p.visual_capture || p.screenshot;
    if (!img) return null;
    if (img.startsWith('http')) return img;
    if (img.startsWith('captures/')) {
      return `/api/${img}`;
    }
    return img;
  };

  return (
    <div className="flex flex-col min-h-screen bg-background">
      {/* TopAppBar (Queue Specific) */}
      <header className="bg-surface-container-lowest w-full sticky top-0 z-40 border-b border-outline-variant hidden md:block">
        <div className="flex justify-between items-center px-6 h-16">
          <div className="flex items-center gap-4">
            <Link href="/queues" className="hover:bg-surface-bright transition-colors p-2 rounded-full active:scale-95 duration-100 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary">arrow_back</span>
            </Link>
            <h1 className="font-headline-md text-headline-md text-primary capitalize">Cola: {niche}</h1>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-4 md:p-6 lg:px-12 bg-surface-container-lowest pb-32 md:pb-12">
        
        {/* Mobile Header (Fallback) */}
        <div className="md:hidden flex items-center gap-3 mb-6">
          <Link href="/queues" className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface">
            <span className="material-symbols-outlined block">arrow_back</span>
          </Link>
          <h1 className="text-xl font-bold text-primary capitalize">Cola: {niche}</h1>
        </div>

        {/* Global Actions */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8 max-w-5xl mx-auto">
          <button 
            onClick={() => setEditingProduct({
              title: '', list_price: '', offer_price: '', discount: '', 
              affiliate_url: '', image_url: '', screenshot: '', id: '', script: []
            })}
            className="flex items-center justify-center gap-3 py-5 px-6 bg-primary text-on-primary hover:brightness-110 transition-all group rounded-xl active:scale-[0.98] shadow-md shadow-primary/20"
          >
            <span className="material-symbols-outlined group-hover:scale-110 transition-transform">
              add_circle
            </span>
            <span className="font-headline-md text-lg">
              Añadir Producto
            </span>
          </button>
          
          <button 
            onClick={handleRefillQueue}
            disabled={isRefilling}
            className="flex items-center justify-center gap-3 py-5 px-6 bg-surface-container-high border border-primary-container/30 hover:border-primary-container transition-all group rounded-xl active:scale-[0.98] disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-primary-container group-hover:scale-110 transition-transform ${isRefilling ? 'animate-spin' : ''}`}>
              autorenew
            </span>
            <span className="font-headline-md text-lg text-primary-container">
              {isRefilling ? 'Iniciando...' : 'Auto-Llenar Cola'}
            </span>
          </button>
          
          <button 
            onClick={handleClearQueue}
            className="flex items-center justify-center gap-3 py-5 px-6 bg-surface-container-high border border-error/20 hover:border-error transition-all group rounded-xl active:scale-[0.98]"
          >
            <span className="material-symbols-outlined text-error group-hover:scale-110 transition-transform">
              delete_sweep
            </span>
            <span className="font-headline-md text-lg text-error">
              Vaciar Cola
            </span>
          </button>
        </section>

        {/* Queue Items List */}
        <section className="flex flex-col gap-6 max-w-[1400px] mx-auto w-full">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-label-caps text-xs text-on-surface-variant tracking-widest uppercase">
              ACTIVE QUEUE ({products.length} ITEMS)
            </h2>
            <div className="flex items-center gap-2">
              <span className="font-status-indicator text-[11px] text-primary opacity-60">
                [SYSTEM_IDLE]
              </span>
            </div>
          </div>

          {/* Search Bar */}
          <div className="relative mb-2">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[18px]">search</span>
            <input
              type="text"
              placeholder="Buscar por título o ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-surface-container border border-outline-variant rounded-xl py-2 pl-9 pr-4 text-sm text-on-surface outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
            />
          </div>

          {/* Controls Bar: Sorting Filter Pills & Save to Queue Action */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-2 bg-surface-container-low border border-outline-variant/30 p-2.5 rounded-xl">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-on-surface-variant font-medium mr-1 flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">sort</span>
                Vista:
              </span>
              <button
                onClick={() => setSortBy('default')}
                className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                  sortBy === 'default'
                    ? 'bg-primary text-on-primary shadow-sm'
                    : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
                }`}
              >
                Cola Real (FIFO)
              </button>
              <button
                onClick={() => setSortBy('savings_desc')}
                className={`px-3 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
                  sortBy === 'savings_desc'
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'bg-surface-container text-emerald-400 hover:bg-emerald-500/10'
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">payments</span>
                Mayor Ahorro ($)
              </button>
              <button
                onClick={() => setSortBy('discount_desc')}
                className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                  sortBy === 'discount_desc'
                    ? 'bg-primary text-on-primary shadow-sm'
                    : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
                }`}
              >
                Mayor Dto (%)
              </button>
              <button
                onClick={() => setSortBy('price_asc')}
                className={`px-3 py-1 rounded-lg font-medium transition-colors ${
                  sortBy === 'price_asc'
                    ? 'bg-primary text-on-primary shadow-sm'
                    : 'bg-surface-container text-on-surface-variant hover:text-on-surface'
                }`}
              >
                Menor Precio
              </button>
            </div>

            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={handleGenerateAffiliates}
                disabled={isGeneratingAffiliates || products.length === 0}
                className="px-3.5 py-1.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white text-xs font-bold rounded-lg shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
                title="Convierte en segundo plano todas las URLs pendientes de Mercado Libre en links de afiliado meli.la usando la sesión activa del servidor"
              >
                <span className={`material-symbols-outlined text-[16px] ${isGeneratingAffiliates ? 'animate-spin' : ''}`}>
                  {isGeneratingAffiliates ? 'sync' : 'link'}
                </span>
                {isGeneratingAffiliates ? 'Generando...' : 'Generar Links Meli.la'}
              </button>

              <button
                onClick={handleSortQueueBySavings}
                disabled={isSortingQueue || products.length === 0}
                className="px-3.5 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold rounded-lg shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
                title="Reordena físicamente el archivo JSON en el servidor para que el bot publique primero los productos con más pesos de ahorro"
              >
                <span className={`material-symbols-outlined text-[16px] ${isSortingQueue ? 'animate-spin' : ''}`}>
                  {isSortingQueue ? 'sync' : 'auto_fix_high'}
                </span>
                {isSortingQueue ? 'Reordenando...' : 'Reordenar Cola por Mayor Ahorro ($)'}
              </button>
            </div>
          </div>

          {displayedProducts.length === 0 ? (
            <div className="p-12 border border-dashed border-outline-variant rounded-xl text-center flex flex-col items-center">
              <span className="material-symbols-outlined text-on-surface-variant text-5xl mb-4">inbox</span>
              <p className="font-body-lg text-on-surface-variant">
                {products.length === 0 ? 'No hay productos en esta cola.' : 'No se encontraron productos que coincidan con la búsqueda.'}
              </p>
              <p className="text-sm text-on-surface-variant/70 mt-2">
                {products.length === 0 ? 'Usa el botón de Auto-Llenar para generar contenido.' : 'Intenta con otro término o limpia el buscador.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {displayedProducts.map((p, idx) => (
                <div key={`${p.id || 'item'}-${idx}`} className="bg-surface-container-low border border-outline-variant/20 rounded-xl overflow-hidden hover:border-primary/50 transition-colors flex flex-col shadow-sm">
                
                {/* Content Section (Top) */}
                <div className="relative">
                  <div className="w-full h-56 bg-white overflow-hidden flex items-center justify-center relative">
                    {resolveImage(p) ? (
                      <img src={resolveImage(p)} alt={p.id} className="w-full h-full object-contain p-4" />
                    ) : (
                      <div className="flex flex-col items-center text-zinc-400">
                        <span className="material-symbols-outlined text-4xl mb-2">image_not_supported</span>
                        <span className="text-xs font-bold">Sin Imagen</span>
                      </div>
                    )}
                    {/* Action: Open Link Overlay Button */}
                    {(p.affiliate_url || p.url) && (
                      <a 
                        href={p.affiliate_url || p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="absolute top-3 left-3 bg-surface-container-high/90 text-on-surface hover:text-primary-container p-2 rounded-lg border border-outline-variant shadow-lg backdrop-blur-md transition-colors"
                        title="Abrir enlace en nueva pestaña"
                      >
                        <span className="material-symbols-outlined text-[20px]">open_in_new</span>
                      </a>
                    )}
                    {/* Action: Edit Overlay Button */}
                    <button 
                      onClick={() => setEditingProduct(p)}
                      className="absolute top-3 right-3 bg-surface-container-high/90 text-on-surface hover:text-primary-container p-2 rounded-lg border border-outline-variant shadow-lg backdrop-blur-md transition-colors"
                      title="Editar Producto"
                    >
                      <span className="material-symbols-outlined text-[20px]">edit</span>
                    </button>
                    {/* Alerta de Link Faltante */}
                    {(() => {
                      const isML = (p.id || '').startsWith("MLM") || (p.affiliate_url || p.url || "").includes("mercadolibre");
                      const isMissingAffiliate = isML && !(p.affiliate_url || p.url || "").includes("meli.la");
                      if (isMissingAffiliate) {
                        return (
                          <div className="absolute top-3 right-16 flex items-center gap-2 z-20">
                            <span className="bg-error text-on-error text-[10px] font-bold px-2 py-1.5 rounded-lg shadow-lg flex items-center gap-1 animate-pulse border border-error/50">
                              <span className="material-symbols-outlined text-[14px]">warning</span>
                              Sin Link Afiliado
                            </span>
                            <button
                              onClick={async () => {
                                try {
                                  const res = await apiFetch(`/api/queues/${niche}/${p.id}/retry-affiliate`, { method: 'POST' });
                                  if (res.ok) {
                                    alert('Generando link en segundo plano... espera unos 30 segundos y recarga la página.');
                                  } else {
                                    alert('Error al iniciar el reintento.');
                                  }
                                } catch (e) {
                                  alert('Error de conexión.');
                                }
                              }}
                              className="bg-surface-container-high/90 text-on-surface hover:text-primary-container p-1.5 rounded-lg border border-outline-variant shadow-lg backdrop-blur-md transition-colors"
                              title="Reintentar Generar Link"
                            >
                              <span className="material-symbols-outlined text-[18px]">sync</span>
                            </button>
                          </div>
                        );
                      }
                      return null;
                    })()}
                  </div>
                  
                  <div className="p-4 md:p-5 bg-gradient-to-t from-surface-container-low via-surface-container-low/90 to-transparent pt-12 -mt-16 relative z-10">
                    <h3 className="font-headline-md text-lg text-on-surface leading-tight mb-2 line-clamp-2">
                      {p.title || p.id}
                    </h3>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="bg-primary-container/20 text-primary px-2 py-0.5 rounded font-status-indicator text-[11px] font-bold border border-primary-container/10">
                        {p.offer_price || 'N/A'}
                      </span>
                      {p.discount && (
                        <span className="bg-error/20 text-error px-2 py-0.5 rounded font-status-indicator text-[11px] font-bold border border-error/10">
                          {p.discount}
                        </span>
                      )}
                      {(() => {
                        const parsePrice = (str: any) => {
                          if (!str) return 0;
                          let s = String(str).replace(/\$/g, '').trim();
                          if (/,\d{1,2}$/.test(s)) {
                            s = s.replace(/,(\d{1,2})$/, '.$1');
                          }
                          s = s.replace(/,/g, '').replace(/[^0-9.]/g, '');
                          return parseFloat(s) || 0;
                        };
                        const list = parsePrice(p.list_price || p.original_price);
                        const offer = parsePrice(p.offer_price);
                        if (list > offer && list > 0) {
                          return (
                            <span className="bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded font-status-indicator text-[11px] font-bold border border-emerald-500/20">
                              Ahorro: ${(list - offer).toFixed(0)}
                            </span>
                          );
                        }
                        return null;
                      })()}
                    </div>
                  </div>
                </div>

                {/* Action Section (Bottom) */}
                <div className="bg-surface-container-high/40 p-4 flex flex-wrap lg:flex-nowrap items-center justify-between gap-4 border-t border-outline-variant/10">
                  
                  {/* Primary Publish Action */}
                  <button 
                    onClick={async () => {
                      if (!confirm('¿Forzar publicación inmediata de este producto?')) return;
                      try {
                        const res = await apiFetch(`/api/queues/${niche}/${p.id}/publish`, { method: 'POST' });
                        if (res.ok) { alert('Publicación iniciada.'); loadData(); }
                      } catch (e) { alert('Error de red'); }
                    }}
                    className="flex-1 w-full lg:w-auto flex items-center justify-center gap-2 bg-primary-container text-on-primary-container py-2.5 px-4 rounded-lg font-bold hover:brightness-110 active:scale-95 transition-all shadow-md shadow-primary-container/20"
                  >
                    <span className="material-symbols-outlined text-[20px]">rocket_launch</span>
                    <span className="text-sm">Publicar Ahora</span>
                  </button>

                  <div className="flex items-center justify-end gap-2 shrink-0">
                    {/* Reorder Actions */}
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={async () => {
                          if (!confirm('¿Mover al inicio?')) return;
                          await apiFetch(`/api/queues/${niche}/${p.id}/reorder`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position: 'top' })
                          });
                          loadData();
                        }}
                        className="w-10 h-10 flex items-center justify-center bg-surface-container border border-outline-variant/30 rounded-lg hover:bg-surface-bright hover:text-primary transition-colors text-on-surface-variant"
                        title="Mover al inicio"
                      >
                        <span className="material-symbols-outlined text-[20px]">arrow_upward</span>
                      </button>
                      <button 
                        onClick={async () => {
                          if (!confirm('¿Mover al final?')) return;
                          await apiFetch(`/api/queues/${niche}/${p.id}/reorder`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position: 'bottom' })
                          });
                          loadData();
                        }}
                        className="w-10 h-10 flex items-center justify-center bg-surface-container border border-outline-variant/30 rounded-lg hover:bg-surface-bright hover:text-primary transition-colors text-on-surface-variant"
                        title="Mover al final"
                      >
                        <span className="material-symbols-outlined text-[20px]">arrow_downward</span>
                      </button>
                    </div>

                    {/* Secondary Actions (Move Niche & Delete) */}
                    <div className="flex items-center gap-2 border-l border-outline-variant/30 pl-2">
                      <select 
                        className="bg-surface-container text-xs text-on-surface-variant rounded-lg p-2.5 h-10 border border-outline-variant/30 outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all cursor-pointer appearance-none px-4"
                        value={niche}
                        onChange={async (e) => {
                          const t = e.target.value;
                          if (t === niche) return;
                          if (!confirm(`¿Mover a la cola de ${t}?`)) {
                            e.target.value = niche;
                            return;
                          }
                          await apiFetch(`/api/queues/${niche}/${p.id}/move_niche`, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_niche: t })
                          });
                          loadData();
                        }}
                        title="Mover a otra cola"
                      >
                        <option value="general">General</option>
                        <option value="moda">Moda</option>
                        <option value="tenis">Tenis</option>
                        <option value="bebes">Bebés</option>
                        <option value="mascotas">Mascotas</option>
                      </select>

                      <button 
                        onClick={() => handleDelete(p.id)}
                        className="w-10 h-10 flex items-center justify-center bg-error/10 border border-error/20 rounded-lg hover:bg-error/20 hover:border-error/40 text-error transition-colors"
                        title="Eliminar producto"
                      >
                        <span className="material-symbols-outlined text-[20px]">delete</span>
                      </button>
                    </div>
                  </div>

                </div>
              </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {/* EDIT MODAL OVERLAY (Restyled) */}
      {editingProduct && (
        <div className="fixed inset-0 z-[100] bg-background/90 backdrop-blur-sm flex flex-col justify-end md:justify-center md:items-center animate-in fade-in duration-200">
          
          <div className="bg-surface-container-low w-full md:w-[900px] md:max-w-[95vw] md:rounded-2xl border-t md:border border-outline-variant flex flex-col max-h-[90vh] shadow-2xl animate-in slide-in-from-bottom-8 duration-300">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 md:p-5 border-b border-outline-variant bg-surface-container-high/50 md:rounded-t-2xl">
              <div className="flex items-center gap-3">
                <button 
                  onClick={() => setEditingProduct(null)}
                  className="p-2 -ml-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-full transition-colors"
                >
                  <span className="material-symbols-outlined">close</span>
                </button>
                <h2 className="text-lg font-headline-md text-on-surface">Editar Producto</h2>
              </div>
              <button 
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-2 text-sm bg-primary-container text-on-primary-container hover:brightness-110 px-5 py-2 rounded-lg font-bold disabled:opacity-50 transition-all active:scale-95"
              >
                <span className="material-symbols-outlined text-[18px]">save</span>
                <span>{saving ? 'Guardando...' : 'Guardar Cambios'}</span>
              </button>
            </div>
            
            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* COLUMN 1: Basic Info */}
                <div className="space-y-5">
                  {/* Title */}
                  <div>
                    <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2">
                      Título / Nombre
                    </label>
                    <textarea 
                      rows={3}
                      className="w-full bg-surface-container border border-outline-variant rounded-xl p-4 text-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all resize-none shadow-inner [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
                      value={editingProduct.title || ''}
                      onChange={e => setEditingProduct({...editingProduct, title: e.target.value})}
                    />
                  </div>

                  {/* Price & Discount */}
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2 truncate" title="Precio Regular">
                        Regular
                      </label>
                      <input 
                        type="text"
                        className="w-full bg-surface-container border border-outline-variant rounded-xl p-3 text-sm text-on-surface-variant line-through focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                        value={editingProduct.original_price || ''}
                        onChange={e => setEditingProduct({...editingProduct, original_price: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2 truncate" title="Precio Oferta">
                        Oferta
                      </label>
                      <input 
                        type="text"
                        className="w-full bg-surface-container border border-outline-variant rounded-xl p-3 text-sm font-bold text-primary focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                        value={editingProduct.offer_price || ''}
                        onChange={e => setEditingProduct({...editingProduct, offer_price: e.target.value})}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2 truncate" title="Descuento">
                        Desc.
                      </label>
                      <input 
                        type="text"
                        className="w-full bg-surface-container border border-outline-variant rounded-xl p-3 text-sm font-bold text-error focus:outline-none focus:border-error focus:ring-1 focus:ring-error transition-all"
                        value={editingProduct.discount || ''}
                        onChange={e => setEditingProduct({...editingProduct, discount: e.target.value})}
                      />
                    </div>
                  </div>

                  {/* Niche */}
                  <div>
                    <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2">
                      Nicho
                    </label>
                    <select 
                      className="w-full bg-surface-container border border-outline-variant rounded-xl p-3 text-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all cursor-pointer appearance-none"
                      value={editingProduct.niche || `[CAT:${niche.toUpperCase()}]`}
                      onChange={e => setEditingProduct({...editingProduct, niche: e.target.value})}
                    >
                      <option value="[CAT:GENERAL]">General</option>
                      <option value="[CAT:BEBES]">Bebés</option>
                      <option value="[CAT:MASCOTAS]">Mascotas</option>
                      <option value="[CAT:MODA]">Moda</option>
                      <option value="[CAT:TENIS]">Tenis</option>
                    </select>
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2">
                      Descripción
                    </label>
                    <textarea 
                      rows={4}
                      className="w-full bg-surface-container border border-outline-variant rounded-xl p-4 text-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all resize-none shadow-inner [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
                      value={editingProduct.description || ''}
                      onChange={e => setEditingProduct({...editingProduct, description: e.target.value})}
                      placeholder="Añade una descripción opcional del producto..."
                    />
                  </div>

                  {/* Image Upload/URL Area */}
                  <div>
                    <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2">
                      Imagen del Producto
                    </label>
                    
                    <div 
                      className={`w-full border-2 border-dashed rounded-xl p-4 transition-all flex flex-col items-center justify-center gap-2 outline-none focus:border-primary focus:bg-surface-container-high
                        ${isUploading ? 'border-primary bg-primary/10' : 'border-outline-variant hover:border-primary-container bg-surface-container'}
                      `}
                      tabIndex={0}
                      onPaste={handlePaste}
                      onDragOver={e => e.preventDefault()}
                      onDrop={e => {
                        e.preventDefault();
                        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                          handleFileUpload(e.dataTransfer.files[0]);
                        }
                      }}
                    >
                      <input 
                        type="file" 
                        id="image-upload-input" 
                        className="hidden" 
                        accept="image/*"
                        onChange={e => {
                          if (e.target.files && e.target.files.length > 0) {
                            handleFileUpload(e.target.files[0]);
                          }
                        }}
                      />
                      
                      {resolveImage(editingProduct) ? (
                        <div className="relative w-full h-32 flex items-center justify-center bg-white rounded-lg overflow-hidden border border-outline-variant/30 pointer-events-none">
                          <img src={resolveImage(editingProduct)} alt="Preview" className="w-full h-full object-contain" />
                        </div>
                      ) : (
                        <span className="material-symbols-outlined text-[24px] text-on-surface-variant pointer-events-none">
                          {isUploading ? 'hourglass_empty' : 'image'}
                        </span>
                      )}
                      
                      <p className="text-xs text-on-surface-variant text-center pointer-events-none mt-1">
                        {isUploading ? (
                          <span className="text-primary font-medium animate-pulse">Subiendo imagen...</span>
                        ) : (
                          <>Clic aquí y presiona <b>Ctrl+V</b> para pegar</>
                        )}
                      </p>
                      
                      {!isUploading && (
                        <button 
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            document.getElementById('image-upload-input')?.click();
                          }}
                          className="mt-2 px-3 py-1 bg-surface-container border border-outline-variant rounded text-[10px] font-medium text-on-surface-variant hover:text-primary hover:border-primary transition-colors cursor-pointer z-10"
                        >
                          O subir archivo...
                        </button>
                      )}
                    </div>

                    <div className="mt-2 flex items-center gap-2">
                      <span className="text-xs text-on-surface-variant whitespace-nowrap">O pega URL:</span>
                      <input 
                        type="text"
                        className="w-full bg-surface-container border border-outline-variant rounded-lg p-2 text-xs text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                        value={editingProduct.image_url || ''}
                        onChange={e => setEditingProduct({
                          ...editingProduct, 
                          image_url: e.target.value,
                          visual_capture: '',
                          screenshot: ''
                        })}
                        placeholder="https://..."
                      />
                    </div>
                  </div>
                </div>

                {/* COLUMN 2: Media & Extra */}
                <div className="space-y-5 flex flex-col">
                  {/* AI Script Section */}
                  <div className="bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/50 flex-1 flex flex-col">
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-xs font-label-caps text-primary-container tracking-widest uppercase flex items-center gap-2">
                        <span className="material-symbols-outlined text-[16px]">smart_toy</span>
                        Guion de Video (IA)
                      </label>
                      <button 
                        onClick={async () => {
                          const btn = document.getElementById('btn-gen-script');
                          if (btn) btn.innerText = 'Generando...';
                          try {
                            const res = await apiFetch(`/api/queues/${niche}/${editingProduct.id}/script`, { method: 'POST' });
                            if (res.ok) {
                              const data = await res.json();
                              setEditingProduct({...editingProduct, tiktok_script: data.script, tts_text: data.script});
                            } else {
                              alert('Error generando guion');
                            }
                          } catch (e) {
                            alert('Error de red al generar guion');
                          }
                          if (btn) btn.innerText = 'Generar Guion';
                        }}
                        id="btn-gen-script"
                        className="text-[10px] font-bold text-on-primary-container bg-primary-container hover:brightness-110 px-3 py-1.5 rounded flex items-center gap-1 transition-all active:scale-95 shrink-0"
                      >
                        <span className="material-symbols-outlined text-[14px]">magic_button</span>
                        Generar
                      </button>
                    </div>
                    <textarea 
                      className="w-full flex-1 min-h-[180px] md:min-h-[260px] bg-surface-container border border-primary-container/20 rounded-lg p-4 text-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all resize-none leading-relaxed shadow-inner font-mono text-[13px] [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
                      value={Array.isArray(editingProduct.script) ? editingProduct.script.join('\n') : (editingProduct.script || editingProduct.tiktok_script || editingProduct.tts_text || '')}
                      onChange={e => {
                        const text = e.target.value;
                        const lines = text.split('\n').filter(l => l.trim() !== '');
                        setEditingProduct({...editingProduct, script: lines, tiktok_script: text, tts_text: text});
                      }}
                      placeholder="El guion de voz generado por la IA aparecerá aquí..."
                    />
                  </div>
                  
                  {/* Affiliate URL */}
                  <div>
                    <label className="block text-xs font-label-caps text-on-surface-variant tracking-widest uppercase mb-2">
                      Enlace de Afiliado (URL)
                    </label>
                    <div className="relative">
                      <input 
                        type="text"
                        className="w-full bg-surface-container border border-outline-variant rounded-xl p-3 pr-10 text-xs text-on-surface focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                        value={editingProduct.affiliate_url !== undefined ? editingProduct.affiliate_url : (editingProduct.url || '')}
                        onChange={e => setEditingProduct({...editingProduct, affiliate_url: e.target.value})}
                        placeholder="https://..."
                      />
                      <a 
                        href={editingProduct.affiliate_url || editingProduct.url || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-on-surface-variant hover:text-primary transition-colors"
                        title="Abrir enlace en nueva pestaña"
                      >
                        <span className="material-symbols-outlined text-[18px]">open_in_new</span>
                      </a>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
