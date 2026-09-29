'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useToast } from '@/components/ui/Toast';

export default function SchedulerPage() {
  const [sched, setSched] = useState<any>({});
  const [activeNetworks, setActiveNetworks] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unsavedChanges, setUnsavedChanges] = useState(false);
  const { success, error } = useToast();

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    Promise.all([
      apiFetch('/api/config/scheduler', { cache: 'no-store' }).then(r => r.json()),
      apiFetch('/api/config/state', { cache: 'no-store' }).then(r => r.json()).catch(() => ({}))
    ])
      .then(([schedData, stateData]) => {
        setSched(schedData || {});
        setActiveNetworks(stateData?.active_networks || {});
        setLoading(false);
      })
      .catch(e => {
        console.error("Error fetching scheduler or state:", e);
        setLoading(false);
      });
  }, []);

  const toggleSlot = (path: string[], hour: number) => {
    setSched((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      
      let target = next;
      for (let i = 0; i < path.length - 1; i++) {
        if (!target[path[i]]) target[path[i]] = {};
        target = target[path[i]];
      }
      
      const lastKey = path[path.length - 1];
      const currentList = Array.isArray(target[lastKey]) ? target[lastKey] : [];
      const currentInts = currentList.map((v: any) => parseInt(v));
      
      let newList;
      if (currentInts.includes(hour)) {
        newList = currentInts.filter((h: number) => h !== hour);
      } else {
        newList = [...currentInts, hour].sort((a: number, b: number) => a - b);
      }
      
      target[lastKey] = newList.map((v: number) => Number(v)); // Asegurar que sean números enteros
      return next;
    });
    setUnsavedChanges(true);
  };

  const toggleUseCustom = (net: string) => {
    setSched((prev: any) => {
      const next = JSON.parse(JSON.stringify(prev));
      if (!next.use_custom) next.use_custom = {};
      next.use_custom[net] = !next.use_custom[net];
      return next;
    });
    setUnsavedChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await apiFetch('/api/config/scheduler', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sched),
      });
      if (res.ok) {
        setUnsavedChanges(false);
        success("Horarios guardados correctamente");
      } else {
        error("Error al guardar horarios");
      }
    } catch (e) {
      error("Error de conexión");
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex-1 max-w-4xl mx-auto w-full p-4 md:p-6 flex justify-center items-center h-[50vh]">
        <div className="animate-pulse text-on-surface-variant flex items-center gap-2">
          <span className="material-symbols-outlined animate-spin">refresh</span>
          Cargando horarios...
        </div>
      </div>
    );
  }

  const generalSlots = (sched.general || []).map((v: any) => parseInt(v));
  const tiktokSlots = (sched.custom?.tiktok || []).map((v: any) => parseInt(v));
  const youtubeSlots = (sched.custom?.youtube || []).map((v: any) => parseInt(v));

  return (
    <div className="flex-1 max-w-4xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 animate-in fade-in duration-500">
      
      {/* Mobile Fallback Header */}
      <div className="md:hidden flex items-center gap-3 mb-6">
        <Link href="/" className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface">
          <span className="material-symbols-outlined block">arrow_back</span>
        </Link>
        <h1 className="text-xl font-bold text-primary">Horarios</h1>
      </div>

      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-outline-variant/50 pb-4 hidden md:flex">
        <div>
          <span className="font-label-caps text-[10px] text-primary-container tracking-widest uppercase">System Automation</span>
          <h2 className="font-headline-md text-2xl text-on-surface">Cronograma de Publicación</h2>
        </div>
      </div>

      {unsavedChanges && (
        <div className="bg-primary/20 border border-primary p-4 rounded-xl flex items-center justify-between shadow-lg shadow-primary/10 animate-in fade-in slide-in-from-top-4">
          <div className="flex items-center gap-2 text-primary font-medium">
            <span className="material-symbols-outlined">info</span>
            <span className="text-sm">Tienes cambios sin guardar</span>
          </div>
          <button 
            onClick={handleSave}
            disabled={saving}
            className="bg-primary text-on-primary hover:bg-primary-container hover:text-on-primary-container px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all active:scale-95 disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[18px]">save</span>
            <span className="font-label-caps uppercase tracking-widest">{saving ? 'Guardando...' : 'Guardar'}</span>
          </button>
        </div>
      )}

      <ScheduleGrid title="Horario Maestro (General)" slots={(sched.general || []).map((v:any)=>parseInt(v))} onToggle={(h) => toggleSlot(['general'], h)} defaultExpanded={true} />
      
      <ScheduleGrid 
        title="Telegram (Global)" 
        slots={(sched.custom?.telegram || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'telegram'], h)} 
        isCustom={sched.use_custom?.telegram} 
        onToggleCustom={() => toggleUseCustom('telegram')} 
        isNetworkActive={activeNetworks.telegram !== false}
      />
      
      <ScheduleGrid 
        title="Facebook (General)" 
        slots={(sched.custom?.facebook || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'facebook'], h)} 
        isCustom={sched.use_custom?.facebook} 
        onToggleCustom={() => toggleUseCustom('facebook')} 
        isNetworkActive={activeNetworks.facebook !== false}
      />

      <ScheduleGrid 
        title="Facebook (Bebés)" 
        slots={(sched.custom?.facebook_bebes || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'facebook_bebes'], h)} 
        isCustom={sched.use_custom?.facebook_bebes} 
        onToggleCustom={() => toggleUseCustom('facebook_bebes')} 
        isNetworkActive={activeNetworks.facebook_bebes !== false}
      />

      <ScheduleGrid 
        title="Facebook (Mascotas)" 
        slots={(sched.custom?.facebook_pets || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'facebook_pets'], h)} 
        isCustom={sched.use_custom?.facebook_pets} 
        onToggleCustom={() => toggleUseCustom('facebook_pets')} 
        isNetworkActive={activeNetworks.facebook_pets !== false}
      />

      <ScheduleGrid 
        title="Facebook (Moda)" 
        slots={(sched.custom?.facebook_moda || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'facebook_moda'], h)} 
        isCustom={sched.use_custom?.facebook_moda} 
        onToggleCustom={() => toggleUseCustom('facebook_moda')} 
        isNetworkActive={activeNetworks.facebook_moda !== false}
      />

      <ScheduleGrid 
        title="Facebook (Tenis)" 
        slots={(sched.custom?.facebook_tenis || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'facebook_tenis'], h)} 
        isCustom={sched.use_custom?.facebook_tenis} 
        onToggleCustom={() => toggleUseCustom('facebook_tenis')} 
        isNetworkActive={activeNetworks.facebook_tenis !== false}
      />

      <ScheduleGrid 
        title="X (Twitter)" 
        slots={(sched.custom?.twitter || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'twitter'], h)} 
        isCustom={sched.use_custom?.twitter} 
        onToggleCustom={() => toggleUseCustom('twitter')} 
        isNetworkActive={activeNetworks.twitter !== false}
      />

      <ScheduleGrid 
        title="TikTok" 
        slots={(sched.custom?.tiktok || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'tiktok'], h)} 
        isCustom={sched.use_custom?.tiktok} 
        onToggleCustom={() => toggleUseCustom('tiktok')} 
        isNetworkActive={activeNetworks.tiktok !== false}
      />
      
      <ScheduleGrid 
        title="YouTube Shorts" 
        slots={(sched.custom?.youtube || []).map((v:any)=>parseInt(v))} 
        onToggle={(h) => toggleSlot(['custom', 'youtube'], h)} 
        isCustom={sched.use_custom?.youtube} 
        onToggleCustom={() => toggleUseCustom('youtube')} 
        isNetworkActive={activeNetworks.youtube !== false}
      />
    </div>
  );
}

function ScheduleGrid({ title, slots, onToggle, isCustom, onToggleCustom, defaultExpanded = false, isNetworkActive = true }: { title: string, slots: number[], onToggle: (h: number) => void, isCustom?: boolean, onToggleCustom?: () => void, defaultExpanded?: boolean, isNetworkActive?: boolean }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded || (isCustom === true));
  const hours = Array.from({ length: 24 }, (_, i) => i);
  // Disabled if it requires a custom toggle but it's OFF, OR if the entire network is disabled globally.
  const disabled = (onToggleCustom && !isCustom) || !isNetworkActive;
  
  return (
    <section className={`bg-surface-container border border-outline-variant rounded-xl shadow-sm transition-opacity ${!isNetworkActive ? 'opacity-50' : (disabled ? 'opacity-50' : 'opacity-100')}`}>
      <div 
        className="flex flex-col sm:flex-row sm:items-center justify-between p-5 gap-3 cursor-pointer select-none hover:bg-surface-container-high/50 rounded-xl transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className={`material-symbols-outlined text-[20px] text-on-surface-variant transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}>expand_more</span>
          <h3 className="text-sm font-label-caps uppercase tracking-widest text-primary flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px]">schedule</span>
            {title}
          </h3>
          {!isNetworkActive && (
            <span className="bg-error/20 text-error border border-error/30 px-2 py-0.5 rounded text-[10px] font-bold font-label-caps uppercase tracking-wider animate-pulse ml-2">
              [INACTIVA EN REDES]
            </span>
          )}
        </div>
        
        {onToggleCustom && (
          <label 
            className="flex items-center gap-2 cursor-pointer group"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="text-xs font-medium text-on-surface-variant group-hover:text-on-surface transition-colors">
              Usar horario independiente
            </span>
            <div className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${isCustom ? 'bg-primary' : 'bg-surface-container-highest border border-outline-variant'}`}>
              <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${isCustom ? 'translate-x-5' : 'translate-x-1'}`} />
            </div>
            <input type="checkbox" className="sr-only" checked={isCustom || false} onChange={onToggleCustom} />
          </label>
        )}
      </div>
      
      {isExpanded && (
        <div className="px-5 pb-5 animate-in slide-in-from-top-2 fade-in duration-200">
          <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 gap-3">
        {hours.map((hour) => {
          const isActive = slots.includes(hour);
          return (
            <button
              key={hour}
              onClick={() => {
                if (disabled) return;
                onToggle(hour);
              }}
              disabled={disabled}
              className={`py-2 px-1 rounded-lg text-xs font-bold transition-all flex flex-col items-center justify-center gap-1 border ${
                isActive 
                  ? (disabled ? 'bg-primary-container/10 text-primary/50 border-primary/20' : 'bg-primary-container/20 text-primary border-primary/50 active:scale-95')
                  : (disabled ? 'bg-surface-container-low text-on-surface-variant/30 border-transparent' : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container-high border-transparent active:scale-95')
              }`}
            >
              <span className={`material-symbols-outlined text-[16px] transition-all ${isActive ? 'text-primary scale-100 opacity-100' : 'scale-50 opacity-0'}`}>
                check_circle
              </span>
              <span>{hour.toString().padStart(2, '0')}:00</span>
            </button>
          );
        })}
          </div>
        </div>
      )}
    </section>
  );
}
