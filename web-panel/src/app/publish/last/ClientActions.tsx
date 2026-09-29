'use client';

import { useState } from 'react';

export default function ClientActions({ productId }: { productId: string }) {
  const [loading, setLoading] = useState<string | null>(null);

  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  const handleAction = async (type: string, url: string, confirmMsg?: string) => {
    if (confirmMsg && !confirm(confirmMsg)) return;
    
    setLoading(type);
    try {
      const method = type === 'delete' ? 'DELETE' : 'POST';
      const res = await apiFetch(url, { method });
      if (res.ok) {
        alert('Acción iniciada correctamente.');
        if (type === 'delete') {
          window.location.href = '/publish';
        }
      } else {
        alert('Error al ejecutar la acción.');
      }
    } catch (error) {
      alert('Error de conexión con el servidor.');
    }
    setLoading(null);
  };

  return (
    <>
      {/* Media Actions */}
      <button 
        onClick={() => handleAction('repub_all', `/api/history/${productId}/republish/all`, '¿Forzar re-publicación en TODAS las redes activas?')}
        disabled={!!loading}
        className="w-full flex items-center justify-center gap-2 py-4 bg-surface-container-high text-on-surface font-label-caps text-xs rounded-xl border border-outline-variant transition-all hover:border-primary/50 active:scale-[0.98] shadow-sm disabled:opacity-50"
      >
        <span className={`material-symbols-outlined text-[18px] text-primary ${loading === 'repub_all' ? 'animate-spin' : ''}`}>
          {loading === 'repub_all' ? 'sync' : 'send'}
        </span>
        Volver a Publicar (Todo)
      </button>

      <button 
        onClick={() => handleAction('video', `/api/history/${productId}/video`, '¿Iniciar creación de Video Premium? Esto tomará unos minutos.')}
        disabled={!!loading}
        className="w-full flex items-center justify-center gap-2 py-4 bg-surface-container-high text-on-surface font-label-caps text-xs rounded-xl border border-outline-variant transition-all hover:border-primary/50 active:scale-[0.98] shadow-sm disabled:opacity-50"
      >
        <span className={`material-symbols-outlined text-[18px] text-primary ${loading === 'video' ? 'animate-spin' : ''}`}>
          {loading === 'video' ? 'sync' : 'video_library'}
        </span>
        CREAR VIDEO PREMIUM
      </button>

      {/* Social Grid */}
      <div className="grid grid-cols-2 gap-2 pt-2">
        <button 
          onClick={() => handleAction('repub_fb', `/api/history/${productId}/republish/facebook`, '¿Publicar solo en Grupos de FB?')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 py-3 bg-surface-container text-on-surface-variant hover:text-on-surface font-label-caps text-[10px] rounded-lg border border-outline-variant/40 hover:bg-surface-container-high active:scale-[0.98] transition-colors disabled:opacity-50"
        >
          <span className="text-blue-400">📘</span> Repub. FB Grupos
        </button>
        <button 
          onClick={() => handleAction('repub_tg', `/api/history/${productId}/republish/telegram`, '¿Publicar solo en Telegram?')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 py-3 bg-surface-container text-on-surface-variant hover:text-on-surface font-label-caps text-[10px] rounded-lg border border-outline-variant/40 hover:bg-surface-container-high active:scale-[0.98] transition-colors disabled:opacity-50"
        >
          <span className="text-sky-400">✈️</span> Repub. Telegram
        </button>
        <button 
          onClick={() => handleAction('repub_pin', `/api/history/${productId}/republish/pinterest`, '¿Publicar solo en Pinterest?')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 py-3 bg-surface-container text-on-surface-variant hover:text-on-surface font-label-caps text-[10px] rounded-lg border border-outline-variant/40 hover:bg-surface-container-high active:scale-[0.98] transition-colors disabled:opacity-50"
        >
          <span className="text-red-400">📌</span> Repub. Pinterest
        </button>
        <button 
          onClick={() => handleAction('repub_web', `/api/history/${productId}/republish/web`, '¿Publicar solo en la Web?')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 py-3 bg-surface-container text-on-surface-variant hover:text-on-surface font-label-caps text-[10px] rounded-lg border border-outline-variant/40 hover:bg-surface-container-high active:scale-[0.98] transition-colors disabled:opacity-50"
        >
          <span className="text-green-400">🌐</span> Repub. Web
        </button>
      </div>

      {/* History Actions */}
      <div className="space-y-3 pt-6 border-t border-outline-variant mt-2">
        <button 
          onClick={() => handleAction('delete', `/api/history/${productId}`, '¿Estás completamente seguro de borrar este producto del historial?')}
          disabled={!!loading}
          className="w-full flex items-center justify-center gap-2 py-4 text-error font-label-caps text-[11px] tracking-widest hover:bg-error/10 rounded-xl transition-all disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[18px]">delete</span>
          Quitar de Historial
        </button>
      </div>
    </>
  );
}
