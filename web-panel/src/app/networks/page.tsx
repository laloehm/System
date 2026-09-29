'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';

export default function NetworksPage() {
  const [state, setState] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unsavedChanges, setUnsavedChanges] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/config/state', {
      cache: 'no-store',
      headers: { 'x-panel-key': 'gangas2026' }
    })
      .then(async r => {
        if (!r.ok) {
          throw new Error(`Error ${r.status}: Servidor no disponible`);
        }
        return r.json();
      })
      .then(d => {
        // Initialize default active_networks if empty
        if (!d.active_networks) {
          d.active_networks = {
            facebook: true, fb_page: true, fb_page_video: false, telegram: true,
            pinterest: true, tiktok: true, youtube: true, twitter: true, web: true,
            facebook_bebes: true, facebook_pets: true, facebook_moda: true, facebook_tenis: true
          };
        }
        setState(d);
        setApiError(null);
        setLoading(false);
      })
      .catch(e => {
        console.error(e);
        setApiError('No se pudo conectar a la API (Puerto 8001). Revisa que el servicio gangas_api esté activo.');
        setLoading(false);
      });
  }, []);

  const handleToggle = (key: string, subKey?: string) => {
    setState((prev: any) => {
      const newState = { ...prev };
      if (subKey) {
        newState[key] = { ...newState[key], [subKey]: !newState[key]?.[subKey] };
      } else {
        newState[key] = !newState[key];
      }
      return newState;
    });
    setUnsavedChanges(true);
  };

  const cycleBlocks = (key: string) => {
    setState((prev: any) => {
      const current = prev[key] || 1;
      const next = current >= 5 ? 1 : current + 1;
      return { ...prev, [key]: next };
    });
    setUnsavedChanges(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/config/state', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'x-panel-key': 'gangas2026' },
        body: JSON.stringify(state),
      });
      if (res.ok) {
        setUnsavedChanges(false);
      } else {
        alert("Error al guardar estado");
      }
    } catch (e) {
      alert("Error de conexión");
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex-1 max-w-4xl mx-auto w-full p-4 flex flex-col justify-center items-center h-[70vh]">
        <span className="material-symbols-outlined animate-spin text-primary-container text-4xl mb-4">progress_activity</span>
        <p className="text-on-surface-variant font-label-caps uppercase tracking-widest">Cargando Redes...</p>
      </div>
    );
  }

  const active = state.active_networks || {};

  return (
    <div className="flex-1 max-w-5xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 animate-in fade-in duration-500 relative">
      
      {/* Mobile Fallback Header */}
      <div className="md:hidden flex items-center gap-3 mb-6">
        <Link href="/" className="p-2 rounded-full hover:bg-surface-container-high bg-surface-container border border-outline-variant text-on-surface">
          <span className="material-symbols-outlined block">arrow_back</span>
        </Link>
        <h1 className="text-xl font-bold text-primary">Redes</h1>
      </div>

      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-outline-variant/50 pb-4 hidden md:flex">
        <div>
          <span className="font-label-caps text-[10px] text-primary-container tracking-widest uppercase">Network Management</span>
          <h2 className="font-headline-md text-2xl text-on-surface">Canales Sociales</h2>
        </div>
        <div className="flex items-center gap-2 text-status-indicator font-label-caps text-[11px] text-on-surface-variant">
          <span className="px-3 py-1 bg-surface-container-high rounded border border-outline-variant/50 flex items-center gap-2">
            SYSTEM STATUS: <span className="text-green-400 font-bold">[READY]</span>
          </span>
        </div>
      </div>

      {/* API Error Banner */}
      {apiError && (
        <div className="bg-error/15 border-2 border-error/50 rounded-xl p-4 flex items-center gap-3 animate-in fade-in duration-300">
          <span className="material-symbols-outlined text-error text-2xl">error</span>
          <div className="flex-1">
            <h4 className="text-sm font-bold text-error">Panel Desconectado</h4>
            <p className="text-xs text-on-surface-variant mt-0.5">{apiError}</p>
          </div>
        </div>
      )}

      {/* Unsaved Changes Banner */}
      {unsavedChanges && (
        <div className="sticky top-20 z-50 animate-in slide-in-from-top-4 duration-300 mb-6">
          <div className="bg-surface-container-high border-2 border-primary-container shadow-lg shadow-primary-container/20 rounded-xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="material-symbols-outlined text-primary-container animate-pulse">warning</span>
              <span className="text-on-surface font-label-caps text-xs uppercase tracking-widest">Cambios sin guardar</span>
            </div>
            <button 
              onClick={handleSave}
              disabled={saving}
              className="bg-primary-container text-on-primary-container hover:brightness-110 px-5 py-2 rounded-lg font-bold flex items-center gap-2 transition-all active:scale-95 disabled:opacity-50 text-sm shadow-md"
            >
              <span className="material-symbols-outlined text-[18px]">save</span>
              <span>{saving ? 'GUARDANDO...' : 'GUARDAR AHORA'}</span>
            </button>
          </div>
        </div>
      )}

      {/* Group Management Button */}
      <div className="mb-4">
        <Link href="/networks/groups">
          <div className="bg-primary-container text-on-primary-container p-4 rounded-xl flex items-center justify-between cursor-pointer hover:brightness-110 transition-all shadow-sm border border-outline-variant/30 group">
            <div className="flex items-center gap-3">
              <span className="material-symbols-outlined text-2xl group-hover:scale-110 transition-transform">group</span>
              <div>
                <h3 className="font-bold">Gestionar URLs de Grupos de FB</h3>
                <p className="text-sm opacity-80">Añadir o eliminar grupos para publicación (General, Bebés, Mascotas, etc.)</p>
              </div>
            </div>
            <span className="material-symbols-outlined">chevron_right</span>
          </div>
        </Link>
      </div>

      {/* Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        
        {/* Group Toggles Card */}
        <div className="bg-surface-container p-4 md:p-5 rounded-xl space-y-4 flex flex-col border border-outline-variant/30 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-label-caps text-xs tracking-widest text-on-surface-variant uppercase">Toggles Principales</h3>
            <span className="material-symbols-outlined text-outline-variant text-sm">settings_input_component</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <NicheToggle label="FB GRUPOS GEN" isOn={active.facebook} onToggle={() => handleToggle('active_networks', 'facebook')} />
            <NicheToggle label="FB GRUPOS BEBES" isOn={active.facebook_bebes} onToggle={() => handleToggle('active_networks', 'facebook_bebes')} />
            <NicheToggle label="FB MASCOTAS" isOn={active.facebook_pets} onToggle={() => handleToggle('active_networks', 'facebook_pets')} />
            <NicheToggle label="FB MODA" isOn={active.facebook_moda} onToggle={() => handleToggle('active_networks', 'facebook_moda')} />
          </div>
          <NicheToggle label="FB TENIS" isOn={active.facebook_tenis} onToggle={() => handleToggle('active_networks', 'facebook_tenis')} fullWidth />
        </div>

        {/* Block Counters Card */}
        <div className="bg-surface-container p-4 md:p-5 rounded-xl space-y-4 flex flex-col border border-outline-variant/30 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-label-caps text-xs tracking-widest text-on-surface-variant uppercase">Estado de Bloques</h3>
            <span className="material-symbols-outlined text-outline-variant text-sm">view_quilt</span>
          </div>
          <p className="text-[11px] text-on-surface-variant/70 mb-2 -mt-3">Haz clic en un bloque para cambiar su cantidad diaria (1-5).</p>
          <div className="grid grid-cols-2 gap-3">
            <BlockCounter label="BLOQUES FB GEN" value={state.fb_split_blocks} onClick={() => cycleBlocks('fb_split_blocks')} />
            <BlockCounter label="BLOQUES FB BEBES" value={state.fb_bebes_split_blocks} onClick={() => cycleBlocks('fb_bebes_split_blocks')} />
            <BlockCounter label="BLOQUES MASCOTAS" value={state.fb_pets_split_blocks} onClick={() => cycleBlocks('fb_pets_split_blocks')} />
            <BlockCounter label="BLOQUES MODA" value={state.fb_moda_split_blocks} onClick={() => cycleBlocks('fb_moda_split_blocks')} />
          </div>
          <BlockCounter label="BLOQUES TENIS" value={state.fb_tenis_split_blocks} onClick={() => cycleBlocks('fb_tenis_split_blocks')} dashed />
        </div>

        {/* Platform Stack Card */}
        <div className="md:col-span-2 bg-surface-container p-4 md:p-5 rounded-xl space-y-4 border border-outline-variant/30 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-label-caps text-xs tracking-widest text-on-surface-variant uppercase">Stack de Plataformas</h3>
            <span className="material-symbols-outlined text-outline-variant text-sm">alternate_email</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            <PlatformToggle label="FB PAGE (IMG/TXT)" icon="pages" isOn={active.fb_page} onToggle={() => handleToggle('active_networks', 'fb_page')} />
            <PlatformToggle label="FB PAGE (VIDEO)" icon="movie" isOn={active.fb_page_video} onToggle={() => handleToggle('active_networks', 'fb_page_video')} />
            <PlatformToggle label="TELEGRAM" icon="send" isOn={active.telegram} onToggle={() => handleToggle('active_networks', 'telegram')} />
            <PlatformToggle label="YOUTUBE" icon="smart_display" isOn={active.youtube} onToggle={() => handleToggle('active_networks', 'youtube')} />
            <PlatformToggle label="TIKTOK" icon="play_arrow" isOn={active.tiktok} onToggle={() => handleToggle('active_networks', 'tiktok')} />
            <PlatformToggle label="PINTEREST" icon="push_pin" isOn={active.pinterest} onToggle={() => handleToggle('active_networks', 'pinterest')} />
            <PlatformToggle label="TWITTER / X" icon="tag" isOn={active.twitter} onToggle={() => handleToggle('active_networks', 'twitter')} />
            <PlatformToggle label="WEB (BLOG)" icon="language" isOn={active.web} onToggle={() => handleToggle('active_networks', 'web')} />
          </div>
        </div>

      </div>
    </div>
  );
}

// Subcomponents for the UI

function NicheToggle({ label, isOn, onToggle, fullWidth = false }: { label: string, isOn: boolean, onToggle: () => void, fullWidth?: boolean }) {
  const baseClass = "flex items-center justify-center gap-2 p-3 border rounded-lg transition-all active:scale-95 text-[11px] font-label-caps tracking-widest uppercase cursor-pointer select-none";
  const onClass = "bg-surface-container-highest hover:bg-secondary-container border-outline-variant/50 text-on-surface";
  const offClass = "bg-surface-container-low hover:bg-surface-container-highest border-outline-variant/30 text-on-surface-variant/60";
  
  return (
    <div 
      onClick={onToggle}
      className={`${baseClass} ${isOn ? onClass : offClass} ${fullWidth ? 'w-full' : ''}`}
    >
      <span className={`font-status-indicator text-xs font-bold ${isOn ? 'text-primary-container drop-shadow-[0_0_2px_rgba(56,189,248,0.5)]' : 'text-error/70'}`}>
        [{isOn ? 'ON' : 'OFF'}]
      </span>
      <span>{label}</span>
    </div>
  );
}

function BlockCounter({ label, value = 1, onClick, dashed = false }: { label: string, value: number, onClick: () => void, dashed?: boolean }) {
  return (
    <div 
      onClick={onClick}
      className={`flex items-center justify-center p-3 bg-surface-container-lowest rounded-lg cursor-pointer select-none hover:bg-surface-container-high transition-colors active:scale-95 group border ${dashed ? 'border-dashed border-outline-variant/50' : 'border-solid border-outline-variant/30'}`}
    >
      <span className="font-label-caps text-[10px] tracking-widest text-on-surface-variant uppercase">
        {label}: <span className="text-primary-container font-bold group-hover:text-primary transition-colors">[{value}]</span>
      </span>
    </div>
  );
}

function PlatformToggle({ label, icon, isOn, onToggle }: { label: string, icon: string, isOn: boolean, onToggle: () => void }) {
  return (
    <div 
      onClick={onToggle}
      className={`flex items-center justify-between px-4 py-3 border rounded-lg transition-all active:scale-95 cursor-pointer select-none group ${isOn ? 'bg-surface-container-highest hover:bg-secondary-container border-outline-variant/50' : 'bg-surface-container-low hover:bg-surface-container border-outline-variant/30 opacity-70'}`}
    >
      <div className="flex items-center gap-3">
        <span className={`material-symbols-outlined text-[18px] ${isOn ? 'text-on-surface' : 'text-on-surface-variant'}`}>{icon}</span>
        <span className={`font-label-caps text-[11px] tracking-widest uppercase ${isOn ? 'text-on-surface font-bold' : 'text-on-surface-variant'}`}>{label}</span>
      </div>
      <span className={`font-status-indicator text-xs font-bold transition-colors ${isOn ? 'text-primary drop-shadow-[0_0_3px_rgba(142,213,255,0.4)]' : 'text-on-surface-variant/40'}`}>
        {isOn ? '[ACTIVE]' : '[INACTIVE]'}
      </span>
    </div>
  );
}
