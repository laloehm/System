'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

export default function PublishPage() {
  const [publishing, setPublishing] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toLocaleTimeString('es-ES', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: true 
      }).toLowerCase());
    };
    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  const handlePublish = async (network: string) => {
    setPublishing(network);
    try {
      const path = `/api/bot/publish/${network}`;
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'x-panel-key': 'gangas2026' }
      });

      if (res.ok) {
        alert(`Publicación en ${network.toUpperCase()} iniciada con éxito.`);
      } else {
        alert(`Error al publicar en ${network}`);
      }
    } catch (e) {
      alert('Error de conexión');
    }
    setPublishing(null);
  };

  return (
    <div className="flex-1 max-w-2xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 animate-in fade-in duration-500">
      <section className="bg-surface-container-low border border-surface-variant rounded-xl overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="p-4 md:p-6 flex justify-between items-center bg-surface-container-high/50 border-b border-outline-variant">
          <div className="flex items-center gap-3">
            <span className="text-xl">🚀</span>
            <h1 className="font-headline-md text-xl md:text-2xl text-on-surface">Publicación</h1>
          </div>
          <span className="font-label-caps text-[12px] text-on-surface-variant opacity-60">
            {currentTime}
          </span>
        </div>

        {/* Action Grid */}
        <div className="p-4 md:p-6 space-y-4">
          {/* Global Action */}
          <button 
            onClick={() => handlePublish('global')}
            disabled={publishing !== null}
            className="w-full py-6 bg-primary-container text-on-primary-container hover:bg-primary hover:shadow-[0_0_15px_rgba(56,189,248,0.3)] rounded-xl shadow-lg flex items-center justify-center gap-3 active:scale-[0.98] transition-all group disabled:opacity-50"
          >
            <span className={`material-symbols-outlined ${publishing === 'global' ? 'animate-spin' : 'group-hover:animate-pulse'}`}>
              public
            </span>
            <span className="font-label-caps text-[14px] md:text-[16px] tracking-wider uppercase font-bold">
              Publicar Sig (Global)
            </span>
          </button>

          {/* Split Grid Rows */}
          <div className="grid grid-cols-2 gap-4">
            <button 
              onClick={() => handlePublish('telegram')}
              disabled={publishing !== null}
              className="bg-surface-container hover:bg-surface-container-high border border-outline-variant hover:border-outline py-4 rounded-xl flex flex-col items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-primary ${publishing === 'telegram' ? 'animate-spin' : ''}`}>send</span>
              <span className="font-label-caps text-[10px] uppercase font-bold text-on-surface-variant">Pub Sig (Solo TG)</span>
            </button>
            <button 
              onClick={() => handlePublish('facebook')}
              disabled={publishing !== null}
              className="bg-surface-container hover:bg-surface-container-high border border-outline-variant hover:border-outline py-4 rounded-xl flex flex-col items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-primary ${publishing === 'facebook' ? 'animate-spin' : ''}`}>facebook</span>
              <span className="font-label-caps text-[10px] uppercase font-bold text-on-surface-variant">Pub Sig (Solo FB)</span>
            </button>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <button 
              onClick={() => handlePublish('pinterest')}
              disabled={publishing !== null}
              className="bg-surface-container hover:bg-surface-container-high border border-outline-variant hover:border-outline py-4 rounded-xl flex flex-col items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-primary ${publishing === 'pinterest' ? 'animate-spin' : ''}`}>push_pin</span>
              <span className="font-label-caps text-[10px] uppercase font-bold text-on-surface-variant">Pub Sig (Solo PINT)</span>
            </button>
            <button 
              onClick={() => handlePublish('twitter')}
              disabled={publishing !== null}
              className="bg-surface-container hover:bg-surface-container-high border border-outline-variant hover:border-outline py-4 rounded-xl flex flex-col items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-primary ${publishing === 'twitter' ? 'animate-spin' : ''}`}>tag</span>
              <span className="font-label-caps text-[10px] uppercase font-bold text-on-surface-variant">Pub Sig (Solo TW)</span>
            </button>
            <button 
              onClick={() => handlePublish('video')}
              disabled={publishing !== null}
              className="bg-primary-container/10 border border-primary/30 hover:bg-primary-container/20 py-4 rounded-xl flex flex-col items-center justify-center gap-2 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-primary ${publishing === 'video' ? 'animate-spin' : ''}`}>video_library</span>
              <span className="font-label-caps text-[10px] uppercase font-bold text-primary">Video Prem</span>
            </button>
          </div>

          {/* Secondary */}
          <div className="space-y-3 pt-4 border-t border-outline-variant mt-4">
            <Link href="/publish/last" className="w-full py-4 bg-surface-container hover:bg-surface-container-high border border-outline-variant rounded-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-all text-on-surface-variant hover:text-on-surface">
              <span className="material-symbols-outlined text-[18px]">visibility</span>
              <span className="font-label-caps text-[12px] uppercase font-bold">Ver Último Publicado</span>
            </Link>

          </div>
        </div>
      </section>
    </div>
  );
}
