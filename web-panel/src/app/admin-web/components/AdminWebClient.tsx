'use client';
import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminWebClient() {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [editingProduct, setEditingProduct] = useState<any | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const router = useRouter();

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers = {
      ...(options?.headers || {}),
      'x-panel-key': 'gangas2026',
    };
    return fetch(path, { ...options, headers });
  };

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/admin/web');
      if (res.ok) {
        const data = await res.json();
        setHistory(data.web_products || []);
      } else {
        setError('No se pudo cargar la base de datos web.');
      }
    } catch (e) {
      setError('Error de conexión.');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const filteredHistory = useMemo(() => {
    if (!searchTerm) return history;
    const lowerSearch = searchTerm.toLowerCase();
    return history.filter(p => 
      (p.title && p.title.toLowerCase().includes(lowerSearch)) ||
      (p.id && String(p.id).toLowerCase().includes(lowerSearch))
    );
  }, [history, searchTerm]);

  const handleEditClick = (product: any) => {
    setEditingProduct({ ...product });
  };

  const handleDelete = async (productId: string) => {
    if (!confirm('¿Estás seguro de eliminar este producto de la web? Se lanzará una actualización a GitHub automáticamente.')) return;
    
    try {
      const res = await apiFetch(`/api/admin/web/${productId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        alert('Producto eliminado. Actualizando web en segundo plano...');
        fetchHistory();
      } else {
        alert('Error al eliminar producto.');
      }
    } catch (e) {
      alert('Error de red.');
    }
  };

  const handleSaveEdit = async () => {
    if (!editingProduct) return;
    setIsSaving(true);
    try {
      const res = await apiFetch(`/api/admin/web/${editingProduct.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingProduct)
      });
      if (res.ok) {
        alert('Cambios guardados. Actualizando web en segundo plano...');
        setEditingProduct(null);
        fetchHistory();
      } else {
        alert('Error al guardar cambios.');
      }
    } catch (e) {
      alert('Error de conexión.');
    }
    setIsSaving(false);
  };

  return (
    <div className="w-full">
      {/* Mobile Back Button */}
      <div className="md:hidden flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface">
          <span className="material-symbols-outlined block">arrow_back</span>
        </button>
        <h1 className="text-xl font-bold text-primary">Web Admin</h1>
      </div>

      {/* Header Section */}
      <div className="bg-surface-container p-6 rounded-xl mb-6 border-l-4 border-l-primary-container shadow-sm border-t border-r border-b border-outline-variant/30">
        <div className="flex items-center gap-3 mb-2">
          <span className="material-symbols-outlined text-primary-container text-2xl">language</span>
          <h2 className="font-headline-md text-xl text-on-surface truncate">Administrar Web</h2>
        </div>
        <p className="font-body-sm text-on-surface-variant">
          Mostrando los {history.length} productos registrados en la base de datos web (website_db.json).
        </p>
      </div>

      {loading ? (
        <div className="text-center p-10 flex flex-col items-center">
          <span className="material-symbols-outlined animate-spin text-primary-container text-4xl mb-4">progress_activity</span>
          <p className="text-on-surface-variant font-label-caps uppercase tracking-widest">Cargando Datos Web...</p>
        </div>
      ) : error ? (
        <div className="bg-error/10 border border-error/30 rounded-xl p-4 flex items-center gap-3">
          <span className="material-symbols-outlined text-error">error</span>
          <p className="text-sm font-body-sm text-error">{error}</p>
        </div>
      ) : history.length === 0 ? (
        <div className="p-12 border border-dashed border-outline-variant rounded-xl text-center flex flex-col items-center">
          <span className="material-symbols-outlined text-on-surface-variant text-5xl mb-4">language</span>
          <p className="font-body-lg text-on-surface-variant">La base de datos web está vacía.</p>
        </div>
      ) : (
        <>
          {/* Action Buttons (Search) */}
          <div className="mb-6 flex">
            <div className="flex-1 flex items-center gap-3 p-4 bg-surface-container focus-within:bg-surface-bright focus-within:border-primary border border-outline-variant rounded-lg text-on-surface-variant transition-colors cursor-text">
              <span className="material-symbols-outlined text-primary-container">search</span>
              <input 
                type="text" 
                placeholder="Buscar por nombre o ID..." 
                className="bg-transparent border-none outline-none w-full text-on-surface font-body-sm placeholder:text-on-surface-variant/50"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
          </div>

          {/* Product Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredHistory.map((p, idx) => (
              <div 
                key={idx} 
                className="w-full flex items-center bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant rounded-lg text-left group p-3 transition-all"
              >
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
                    <span className="text-primary-container font-label-caps text-[10px] font-bold tracking-wider">{p.price || p.offer_price || '$?'}</span>
                    <span className="w-1 h-1 rounded-full bg-outline-variant"></span>
                    <span className="text-on-surface-variant font-label-caps text-[10px] uppercase tracking-wider capitalize">{p.niche || 'General'}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1">
                  <button 
                    onClick={() => handleEditClick(p)}
                    className="p-2.5 rounded-full bg-surface-container hover:bg-primary/20 text-on-surface-variant hover:text-primary transition-all active:scale-90 shadow-sm border border-outline-variant/30"
                    title="Editar producto"
                  >
                    <span className="material-symbols-outlined text-[20px]">edit</span>
                  </button>
                  <button 
                    onClick={() => handleDelete(p.id)}
                    className="p-2.5 rounded-full bg-surface-container hover:bg-error/20 text-on-surface-variant hover:text-error transition-all active:scale-90 shadow-sm border border-outline-variant/30"
                    title="Eliminar producto"
                  >
                    <span className="material-symbols-outlined text-[20px]">delete</span>
                  </button>
                  <a 
                    href={p.url || p.affiliate_url || '#'} 
                    target="_blank" 
                    rel="noreferrer"
                    className="p-2.5 rounded-full bg-surface-container hover:bg-primary/20 text-on-surface-variant hover:text-primary transition-all active:scale-90 shadow-sm border border-outline-variant/30"
                    title="Abrir link original"
                  >
                    <span className="material-symbols-outlined text-[20px]">open_in_new</span>
                  </a>
                </div>
              </div>
            ))}
            
            {filteredHistory.length === 0 && (
              <div className="col-span-1 md:col-span-2 text-center p-8 text-on-surface-variant">
                No se encontraron productos que coincidan con la búsqueda.
              </div>
            )}
          </div>
        </>
      )}

      {/* Edit Modal */}
      {editingProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 px-4">
          <div className="bg-surface-container-high border border-outline-variant rounded-xl w-[90vw] max-w-[500px] shadow-2xl flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between p-4 border-b border-outline-variant/50">
              <h2 className="font-headline-sm text-lg text-on-surface">Editar Producto</h2>
              <button 
                onClick={() => setEditingProduct(null)} 
                className="p-2 rounded-full hover:bg-surface-container-highest text-on-surface-variant transition-colors"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              <div>
                <label className="block text-xs font-label-caps uppercase text-on-surface-variant mb-1">Título</label>
                <input 
                  type="text" 
                  value={editingProduct.title || ''} 
                  onChange={e => setEditingProduct({...editingProduct, title: e.target.value})}
                  className="w-full bg-surface-container border border-outline-variant rounded-lg p-3 text-on-surface focus:border-primary outline-none transition-colors"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-label-caps uppercase text-on-surface-variant mb-1">Precio Normal</label>
                  <input 
                    type="text" 
                    value={editingProduct.price || ''} 
                    onChange={e => setEditingProduct({...editingProduct, price: e.target.value})}
                    className="w-full bg-surface-container border border-outline-variant rounded-lg p-3 text-on-surface focus:border-primary outline-none transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-xs font-label-caps uppercase text-on-surface-variant mb-1">Precio Oferta</label>
                  <input 
                    type="text" 
                    value={editingProduct.offer_price || ''} 
                    onChange={e => setEditingProduct({...editingProduct, offer_price: e.target.value})}
                    className="w-full bg-surface-container border border-outline-variant rounded-lg p-3 text-on-surface focus:border-primary outline-none transition-colors"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-label-caps uppercase text-on-surface-variant mb-1">Nicho / Categoría</label>
                <input 
                  type="text" 
                  value={editingProduct.niche || ''} 
                  onChange={e => setEditingProduct({...editingProduct, niche: e.target.value})}
                  className="w-full bg-surface-container border border-outline-variant rounded-lg p-3 text-on-surface focus:border-primary outline-none transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-label-caps uppercase text-on-surface-variant mb-1">URL de Imagen</label>
                <input 
                  type="text" 
                  value={editingProduct.image_url || ''} 
                  onChange={e => setEditingProduct({...editingProduct, image_url: e.target.value})}
                  className="w-full bg-surface-container border border-outline-variant rounded-lg p-3 text-on-surface focus:border-primary outline-none transition-colors"
                />
              </div>
            </div>

            <div className="p-4 border-t border-outline-variant/50 flex justify-end gap-3 bg-surface-container-low rounded-b-xl">
              <button 
                onClick={() => setEditingProduct(null)}
                disabled={isSaving}
                className="px-5 py-2.5 rounded-lg text-sm font-label-caps uppercase text-on-surface hover:bg-surface-container-highest transition-colors disabled:opacity-50"
              >
                Cancelar
              </button>
              <button 
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="px-5 py-2.5 rounded-lg text-sm font-label-caps uppercase bg-primary text-on-primary hover:bg-primary-container hover:text-on-primary-container transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {isSaving ? <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span> : null}
                Guardar y Publicar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

