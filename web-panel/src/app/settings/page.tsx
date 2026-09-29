'use client';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useToast } from '@/components/ui/Toast';

export default function SettingsPage() {
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [restarting, setRestarting] = useState(false);
  const [restartingSystem, setRestartingSystem] = useState(false);
  const [showUserGuide, setShowUserGuide] = useState(false);
  const [scrapingConfig, setScrapingConfig] = useState<Record<string, any>>({});
  const [scrapersStatus, setScrapersStatus] = useState<Record<string, boolean>>({});
  const [savingScraping, setSavingScraping] = useState(false);
  const [loadingScraping, setLoadingScraping] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const { success, error, toast } = useToast();

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  const handleRestart = async () => {
    if (!confirm('¿ESTÁS SEGURO? Esto reiniciará el bot y detendrá cualquier publicación en curso.')) return;
    setRestarting(true);
    try {
      await apiFetch('/api/bot/restart', { method: 'POST' });
      toast('Señal de reinicio enviada. El bot se reiniciará en unos segundos.', 'info');
    } catch (e) {
      console.error(e);
      error('Error de conexión al reiniciar el bot.');
    }
    setRestarting(false);
  };

  const handleRestartSystem = async () => {
    if (!confirm('¿ESTÁS SEGURO? Esto reiniciará el Sistema Completo (Bot, Web y API).')) return;
    setRestartingSystem(true);
    try {
      await apiFetch('/api/system/restart-all', { method: 'POST' });
      toast('Señal de reinicio completo enviada. Los servicios se restablecerán en unos segundos.', 'info');
    } catch (e) {
      console.error(e);
      error('Error de conexión al reiniciar el sistema.');
    }
    setRestartingSystem(false);
  };

  const handleClearLogs = () => {
    if (!confirm('¿Limpiar consola de logs locales?')) return;
    setLogs([]);
  };

  const handleCopyLogs = () => {
    const logsText = (Array.isArray(logs) ? logs : [logs]).join('\n');
    
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(logsText)
        .then(() => toast('Logs copiados al portapapeles', 'success'))
        .catch(() => toast('Error al copiar logs', 'error'));
    } else {
      // Fallback para HTTP (sin SSL)
      const textArea = document.createElement('textarea');
      textArea.value = logsText;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      
      try {
        document.execCommand('copy');
        toast('Logs copiados al portapapeles (Fallback)', 'success');
      } catch (err) {
        console.error('Fallback error:', err);
        toast('No se pudo copiar (HTTP no seguro)', 'error');
      }
      textArea.remove();
    }
  };

  const handleDiscardFailed = async () => {
    if (!confirm('¿Estás seguro de descartar todos los grupos FB fallidos? Se perderán las publicaciones pendientes que fallaron.')) return;
    try {
      const res = await apiFetch('/api/bot/discard-failed', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        toast(data.message || 'Cola de fallidos eliminada.', 'success');
      } else {
        toast(data.detail || 'Error al descartar fallidos.', 'error');
      }
    } catch (e) {
      toast('Error de red al descartar fallidos.', 'error');
    }
  };

  useEffect(() => {
    apiFetch('/api/config/scraping', { cache: 'no-store' })
      .then(async r => (r.ok ? r.json() : null))
      .then(d => {
        if (d) setScrapingConfig(d);
        setLoadingScraping(false);
      })
      .catch(e => {
        console.error("Error loading scraping config:", e);
        setLoadingScraping(false);
      });

    // Cargar estado del usuario (user_state.json) para get allow_duplicate_products
    apiFetch('/api/config/state', { cache: 'no-store' })
      .then(async r => (r.ok ? r.json() : null))
      .then(d => {
        if (d && d.allow_duplicate_products !== undefined) {
          setScrapingConfig(prev => ({...prev, allow_duplicate_products: d.allow_duplicate_products}));
        }
      })
      .catch(e => console.error("Error loading user state:", e));

    apiFetch('/api/scrapers/status', { cache: 'no-store' })
      .then(async r => (r.ok ? r.json() : null))
      .then(d => {
        if (d) setScrapersStatus(d);
      })
      .catch(e => console.error("Error loading scrapers status:", e));
  }, []);

  const handleSaveScraping = async () => {
    setSavingScraping(true);
    try {
      // Filtrar líneas vacías SOLO al guardar
      const cleanedConfig = {...scrapingConfig};
      if (cleanedConfig['excluded_keywords_temp']) {
        cleanedConfig['excluded_keywords'] = cleanedConfig['excluded_keywords_temp']
          .map((k: string) => k.trim())
          .filter((k: string) => k.length > 0);
        delete cleanedConfig['excluded_keywords_temp'];
      }

      const res = await apiFetch('/api/config/scraping', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cleanedConfig),
      });
      if (res.ok) {
        success('Términos de búsqueda guardados correctamente.');
        setScrapingConfig(cleanedConfig);
      } else {
        const errData = await res.json().catch(() => ({}));
        error(errData.detail || `Error al guardar (HTTP ${res.status}).`);
      }
    } catch (e: any) {
      error(e?.message || 'Error de conexión al guardar.');
    }
    setSavingScraping(false);
  };

  // State for lines and scroll
  const [logLines, setLogLines] = useState(50);
  const [autoScroll, setAutoScroll] = useState(false);

  // Poll for logs if panel is open
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (showLogs) {
      interval = setInterval(async () => {
        try {
          const res = await apiFetch(`/api/bot/logs?lines=${logLines}`);
          if (res.ok) {
            const data = await res.json();
            if (data.logs) {
              setLogs(Array.isArray(data.logs) ? data.logs : [data.logs]);
            }
          }
        } catch (e) {
          // Silent fail for polling
        }
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [showLogs, logLines]);

  // Auto-scroll logs
  useEffect(() => {
    if (showLogs && logsEndRef.current && autoScroll) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, showLogs, autoScroll]);

  return (
    <div className="w-full overflow-x-hidden px-4 md:px-0 py-4 space-y-4 pb-32 animate-in fade-in duration-500">
      
      {/* Mobile Fallback Header */}
      <div className="md:hidden flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <Link href="/" className="p-2 hover:bg-surface-container-high rounded-full transition-colors text-on-surface flex items-center justify-center">
            <span className="material-symbols-outlined block">arrow_back</span>
          </Link>
          <h1 className="text-sm font-label-caps tracking-widest uppercase text-on-surface">Command Center</h1>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse shadow-[0_0_8px_#4ade80]"></span>
          <span className="text-[11px] font-label-caps uppercase tracking-widest text-primary">Online</span>
        </div>
      </div>

      {/* Page Header (Desktop) */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-outline-variant/50 pb-4 hidden md:flex">
        <div>
          <span className="font-label-caps text-[10px] text-primary-container tracking-widest uppercase">System Maintenance</span>
          <h2 className="font-headline-md text-2xl text-on-surface">Ajustes</h2>
        </div>
        <div className="flex items-center gap-2 text-status-indicator font-label-caps text-[11px] text-on-surface-variant">
          <span className="px-3 py-1 bg-surface-container-high rounded border border-outline-variant/50 flex items-center gap-2">
            SYSTEM STATUS: <span className="text-green-400 font-bold animate-pulse">[ONLINE]</span>
          </span>
        </div>
      </div>

      {/* Header Card */}
      <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4 shadow-sm">
        <div className="flex items-start gap-3 mb-1">
          <div className="p-2 bg-primary-container/20 rounded-lg shrink-0">
            <span className="material-symbols-outlined text-primary-container text-xl" style={{fontVariationSettings: "'FILL' 1"}}>build</span>
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-on-surface leading-snug">Mantenimiento del Bot</h2>
            <p className="text-sm text-on-surface-variant mt-1 leading-snug">
              Gestiona el estado y registros operativos del sistema automatizado.
            </p>
          </div>
        </div>
      </div>
      
      {/* Scraping Config */}
      <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-primary-container/20 rounded-lg shrink-0">
            <span className="material-symbols-outlined text-primary-container text-xl">search</span>
          </div>
          <h2 className="text-base font-bold text-on-surface leading-snug">Términos de Búsqueda (Apify)</h2>
        </div>
        
        {loadingScraping ? (
          <div className="animate-pulse text-on-surface-variant flex items-center gap-2">
            <span className="material-symbols-outlined animate-spin">refresh</span>
            Cargando configuración...
          </div>
        ) : (
          <div className="space-y-4">
            {['general', 'bebes', 'mascotas', 'tenis', 'moda'].map(niche => (
              <div key={niche} className="flex flex-col md:flex-row md:items-center gap-2">
                <label className="text-sm font-label-caps uppercase text-on-surface-variant md:w-1/4">
                  Nicho {niche}
                </label>
                <input 
                  type="text" 
                  value={scrapingConfig[niche] || ''}
                  onChange={(e) => setScrapingConfig({...scrapingConfig, [niche]: e.target.value})}
                  className="bg-surface-container border border-outline-variant rounded p-2 text-on-surface flex-1 focus:border-primary outline-none transition-colors"
                  placeholder={`Ej: ${niche === 'general' ? 'tecnologia' : niche}`}
                />
              </div>
            ))}
            
            {/* Regla de Ahorro en Pesos */}
            <div className="flex flex-col gap-3 mt-6 pt-4 border-t border-outline-variant/30">
              <h3 className="text-sm font-bold text-on-surface">Regla de Ahorro</h3>
              <p className="text-xs text-on-surface-variant mb-2 leading-relaxed">
                Configura el ahorro mínimo en pesos ($) para aprobar y publicar ofertas automáticamente.
              </p>
              <div className="flex flex-col md:flex-row md:items-center gap-2">
                <label className="text-sm font-label-caps uppercase text-on-surface-variant md:w-2/5">
                  Ahorro Mínimo en Pesos ($)
                </label>
                <input 
                  type="number" 
                  min="0"
                  value={scrapingConfig['min_strict_savings'] ?? 100}
                  onChange={(e) => setScrapingConfig({...scrapingConfig, 'min_strict_savings': parseInt(e.target.value) || 0})}
                  className="bg-surface-container border border-outline-variant rounded p-2 text-on-surface flex-1 focus:border-primary outline-none transition-colors"
                  placeholder="Ej: 100"
                />
              </div>
            </div>
            
            {/* Amazon Pages Config */}
            <div className="flex flex-col md:flex-row md:items-center gap-2 mt-4 pt-4 border-t border-outline-variant/30">
              <label className="text-sm font-label-caps uppercase text-on-surface-variant md:w-2/5">
                Páginas de Amazon a extraer
              </label>
              <input
                type="number"
                min="1"
                max="10"
                value={scrapingConfig['amazon_pages'] || 1}
                onChange={(e) => setScrapingConfig({...scrapingConfig, 'amazon_pages': parseInt(e.target.value) || 1})}
                className="bg-surface-container border border-outline-variant rounded p-2 text-on-surface flex-1 focus:border-primary outline-none transition-colors"
                placeholder="Ej: 1"
              />
            </div>

            {/* Max Price Config */}
            <div className="flex flex-col md:flex-row md:items-center gap-2 mt-4 pt-4 border-t border-outline-variant/30">
              <label className="text-sm font-label-caps uppercase text-on-surface-variant md:w-2/5">
                Precio máximo de productos
              </label>
              <input
                type="number"
                min="100"
                step="100"
                value={scrapingConfig['max_price'] ?? 5000}
                onChange={(e) => setScrapingConfig({...scrapingConfig, 'max_price': parseFloat(e.target.value) || 5000})}
                className="bg-surface-container border border-outline-variant rounded p-2 text-on-surface flex-1 focus:border-primary outline-none transition-colors"
                placeholder="Ej: 5000"
              />
            </div>

            {/* History TTL Config */}
            <div className="flex flex-col md:flex-row md:items-center gap-2 mt-4 pt-4 border-t border-outline-variant/30">
              <label className="text-sm font-label-caps uppercase text-on-surface-variant md:w-2/5">
                Expiración de Historial (Días para reaprobar)
              </label>
              <input
                type="number"
                min="1"
                max="90"
                value={scrapingConfig['history_ttl_days'] ?? 21}
                onChange={(e) => setScrapingConfig({...scrapingConfig, 'history_ttl_days': parseInt(e.target.value) || 21})}
                className="bg-surface-container border border-outline-variant rounded p-2 text-on-surface flex-1 focus:border-primary outline-none transition-colors"
                placeholder="Ej: 21"
              />
            </div>

            {/* Excluded Keywords */}
            <div className="flex flex-col gap-2 mt-4 pt-4 border-t border-outline-variant/30">
              <label className="text-sm font-label-caps uppercase text-on-surface-variant">
                Términos Bloqueados (por línea)
              </label>
              <textarea
                value={(scrapingConfig['excluded_keywords_temp'] ?? scrapingConfig['excluded_keywords'] ?? []).join('\n')}
                onChange={(e) => {
                  setScrapingConfig({...scrapingConfig, 'excluded_keywords_temp': e.target.value.split('\n')});
                }}
                className="bg-surface-container border border-outline-variant rounded p-3 text-on-surface w-full h-64 focus:border-primary outline-none transition-colors resize-y overflow-y-auto font-mono text-sm leading-relaxed whitespace-pre-wrap break-words"
                placeholder="libro&#10;novela&#10;comic&#10;medicamento"
                style={{ fontFamily: 'monospace' }}
              />
              <p className="text-xs text-on-surface-variant">
                Un término por línea. Se bloquean productos que contengan estas palabras (cualquier parte del título).
              </p>
            </div>

            <button 
              onClick={handleSaveScraping}
              disabled={savingScraping}
              className="mt-4 bg-primary text-on-primary hover:bg-primary-container hover:text-on-primary-container px-6 py-3 rounded-lg text-sm font-bold flex items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-50 w-full md:w-auto"
            >
              <span className="material-symbols-outlined text-[18px]">save</span>
              <span className="font-label-caps uppercase tracking-widest">{savingScraping ? 'Guardando...' : 'Guardar Términos'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Auto-Scrapers Switches */}
      <div className="bg-surface-container-low border border-outline-variant rounded-xl p-4 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-primary-container/20 rounded-lg shrink-0">
            <span className="material-symbols-outlined text-primary-container text-xl">smart_toy</span>
          </div>
          <h2 className="text-base font-bold text-on-surface leading-snug">Estado de Auto-Scrapers</h2>
        </div>
        <p className="text-xs text-on-surface-variant mb-4 leading-relaxed">
          Controla qué nichos tienen permiso para rellenar sus colas automáticamente. Si apagas un nicho, el bot ignorará su cola aunque esté vacía.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
          {['general', 'amazon', 'moda', 'pets', 'baby', 'tenis'].map(niche => (
            <div key={niche} className="flex items-center justify-between p-3 bg-surface-container rounded-lg border border-outline-variant/50">
              <span className="text-sm font-bold text-on-surface capitalize">{niche}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={scrapersStatus[niche] ?? true}
                  onChange={async (e) => {
                    const enabled = e.target.checked;
                    setScrapersStatus(s => ({...s, [niche]: enabled}));
                    try {
                      const res = await apiFetch('/api/scrapers/' + niche + '/toggle', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled })
                      });
                      if (res.ok) toast('Estado actualizado', 'success');
                      else toast('Error al actualizar', 'error');
                    } catch {
                      toast('Error de red', 'error');
                      setScrapersStatus(s => ({...s, [niche]: !enabled})); // revert
                    }
                  }}
                />
                <div className="w-11 h-6 bg-surface-container-highest rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-on-surface after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
          ))}
        </div>

        {/* Aceptar Productos Duplicados */}
        <div className="border-t border-outline-variant/30 pt-4">
          <p className="text-xs text-on-surface-variant mb-3 leading-relaxed">
            Cuando está activado, permite agregar a la cola productos que ya fueron publicados anteriormente. Normalmente los duplicados son rechazados.
          </p>
          <div className="flex items-center justify-between p-3 bg-surface-container rounded-lg border border-outline-variant/50">
            <span className="text-sm font-bold text-on-surface">Aceptar Productos Repetidos</span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={scrapingConfig['allow_duplicate_products'] ?? false}
                onChange={async (e) => {
                  const enabled = e.target.checked;
                  setScrapingConfig({...scrapingConfig, 'allow_duplicate_products': enabled});
                  try {
                    const res = await apiFetch('/api/config/state', {
                      method: 'PUT',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ allow_duplicate_products: enabled }),
                    });
                    if (res.ok) {
                      toast(enabled ? 'Duplicados PERMITIDOS' : 'Duplicados RECHAZADOS', 'success');
                    } else {
                      toast('Error al actualizar', 'error');
                    }
                  } catch {
                    toast('Error de red', 'error');
                  }
                }}
              />
              <div className="w-11 h-6 bg-surface-container-highest rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-on-surface after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
            </label>
          </div>
        </div>
      </div>

      {/* Actions List */}
      <div className="space-y-3">
        <Link href="/admin-web" className="w-full bg-surface-container hover:bg-surface-container-high border border-outline-variant py-4 px-6 rounded-xl flex items-center justify-center transition-all active:scale-[0.98] group cursor-pointer">
          <span className="text-xs font-label-caps uppercase text-on-surface group-hover:text-primary-container">Administrar Web</span>
        </Link>
        
        <button 
          onClick={() => setShowLogs(!showLogs)}
          className={`w-full ${showLogs ? 'bg-surface-container-high' : 'bg-surface-container hover:bg-surface-container-high'} border border-outline-variant py-4 px-6 rounded-xl flex items-center justify-center transition-all active:scale-[0.98] group`}
        >
          <span className="text-xs font-label-caps uppercase text-on-surface group-hover:text-primary-container transition-colors">
            {showLogs ? 'Ocultar Logs' : 'Revisar Logs'}
          </span>
        </button>

        {/* Logs Console Container */}
        {showLogs && (
          <div className="flex flex-col gap-2 mt-4 animate-in slide-in-from-top-4 duration-300">
            <div className="flex items-center justify-between px-2">
              <span className="text-xs text-on-surface-variant font-label-caps uppercase">Registro en vivo</span>
              <div className="flex items-center gap-4">
                <button 
                  onClick={handleCopyLogs}
                  className="flex items-center justify-center p-1.5 rounded-md hover:bg-surface-container-highest text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                  title="Copiar Logs"
                >
                  <span className="material-symbols-outlined text-[16px]">content_copy</span>
                </button>
                <label className="flex items-center gap-1.5 cursor-pointer hover:text-primary transition-colors text-on-surface-variant">
                  <input 
                    type="checkbox" 
                    checked={autoScroll} 
                    onChange={(e) => setAutoScroll(e.target.checked)} 
                    className="accent-primary cursor-pointer"
                  />
                  <span className="text-[11px] font-label-caps uppercase">Seguir Scroll</span>
                </label>
                <select 
                  value={logLines}
                  onChange={(e) => setLogLines(Number(e.target.value))}
                  className="bg-surface-container border border-outline-variant rounded p-1 text-xs text-on-surface focus:border-primary outline-none"
                >
                  <option value={20}>Últimas 20 líneas</option>
                  <option value={50}>Últimas 50 líneas</option>
                  <option value={100}>Últimas 100 líneas</option>
                  <option value={200}>Últimas 200 líneas</option>
                  <option value={300}>Últimas 300 líneas</option>
                  <option value={400}>Últimas 400 líneas</option>
                  <option value={500}>Últimas 500 líneas</option>
                </select>
              </div>
            </div>
            <div className="bg-black/80 border border-outline-variant rounded-xl p-4 h-64 md:h-96 overflow-y-auto font-mono text-[11px] md:text-[12px] leading-relaxed shadow-inner">
            {(!logs || logs.length === 0) ? (
              <div className="text-on-surface-variant/50 h-full flex items-center justify-center italic">
                Esperando registros del sistema...
              </div>
            ) : (
              (Array.isArray(logs) ? logs : [logs]).map((log: any, i: number) => (
                <div key={i} className="mb-1">
                  <span className={`${String(log).toLowerCase().includes('error') || String(log).toLowerCase().includes('fail') ? 'text-error' : 'text-primary'}`}>
                    {String(log)}
                  </span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
            </div>
          </div>
        )}

        <button 
          onClick={handleClearLogs}
          className="w-full bg-surface-container hover:bg-surface-container-high disabled:opacity-50 border border-outline-variant py-4 px-6 rounded-xl flex items-center justify-center transition-all active:scale-[0.98] group"
        >
          <span className="text-xs font-label-caps uppercase text-on-surface group-hover:text-primary-container">Limpiar Logs</span>
        </button>

        <button 
          onClick={handleDiscardFailed}
          className="w-full bg-error/10 hover:bg-error/20 border border-error/30 py-4 px-6 rounded-xl flex items-center justify-center transition-all active:scale-[0.98] group cursor-pointer"
        >
          <span className="text-xs font-label-caps uppercase text-error">Descartar Fallidos</span>
        </button>

        <button 
          onClick={handleRestart}
          disabled={restarting}
          className="w-full bg-surface-container hover:bg-surface-container-high border border-outline-variant py-4 px-6 rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98] group cursor-pointer"
        >
          {restarting && <span className="material-symbols-outlined text-[16px] text-error animate-spin">restart_alt</span>}
          <span className="text-xs font-label-caps uppercase text-error group-hover:brightness-110">
            {restarting ? 'Reiniciando...' : 'Reiniciar Bot'}
          </span>
        </button>

        <button 
          onClick={handleRestartSystem}
          disabled={restartingSystem}
          className="w-full bg-error/15 hover:bg-error/25 border border-error/40 py-4 px-6 rounded-xl flex items-center justify-center gap-2 transition-all active:scale-[0.98] group cursor-pointer"
        >
          {restartingSystem && <span className="material-symbols-outlined text-[16px] text-error animate-spin">restart_alt</span>}
          <span className="text-xs font-label-caps uppercase text-error font-bold group-hover:brightness-110">
            {restartingSystem ? 'Reiniciando Sistema...' : 'Reiniciar Sistema Completo'}
          </span>
        </button>
        
        <button 
          onClick={() => setShowUserGuide(true)}
          className="w-full bg-surface-container hover:bg-surface-container-high border border-outline-variant py-4 px-6 rounded-xl flex items-center justify-center gap-3 transition-all active:scale-[0.98] group cursor-pointer"
        >
          <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary-container text-[18px]">menu_book</span>
          <span className="text-xs font-label-caps uppercase text-on-surface group-hover:text-primary-container">Guía de Usuario</span>
        </button>
      </div>

      {/* Modal Guía de Usuario */}
      {showUserGuide && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-surface-container-low border border-outline-variant rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-outline-variant/50">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary-container text-xl">menu_book</span>
                <h3 className="text-base font-bold text-on-surface">Guía Rápida del Sistema Gangas MX</h3>
              </div>
              <button 
                onClick={() => setShowUserGuide(false)}
                className="p-1 rounded-full hover:bg-surface-container-high text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined text-xl">close</span>
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto space-y-5 text-sm text-on-surface-variant leading-relaxed">
              <div>
                <h4 className="font-bold text-on-surface text-sm mb-1.5 flex items-center gap-2">
                  <span className="material-symbols-outlined text-xs text-primary">terminal</span>
                  Comandos de Telegram (Bot de Control)
                </h4>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li><code className="text-primary font-mono">/start</code> — Abre el teclado principal y menú del bot.</li>
                  <li><code className="text-primary font-mono">/reboot</code> o <code className="text-primary font-mono">/reiniciar</code> — Reinicia el sistema completo de forma segura.</li>
                  <li><code className="text-primary font-mono">/status</code> — Muestra diagnóstico rápido en tiempo real.</li>
                </ul>
              </div>

              <div>
                <h4 className="font-bold text-on-surface text-sm mb-1.5 flex items-center gap-2">
                  <span className="material-symbols-outlined text-xs text-primary">restart_alt</span>
                  Mantenimiento y Reinicios
                </h4>
                <p className="text-xs">
                  El sistema corre en Linux bajo servicios de systemd. Si necesitas reiniciar componentes:
                </p>
                <ul className="list-disc list-inside space-y-1 text-xs mt-1">
                  <li><strong>Reiniciar Bot:</strong> Recicla el proceso de búsqueda, scraping y publicaciones sin tocar la API ni el Panel Web.</li>
                  <li><strong>Reiniciar Sistema Completo:</strong> Reinicia simultáneamente el Bot, la API de FastAPI y la interfaz web.</li>
                </ul>
              </div>

              <div>
                <h4 className="font-bold text-on-surface text-sm mb-1.5 flex items-center gap-2">
                  <span className="material-symbols-outlined text-xs text-primary">filter_alt</span>
                  Regla de Ahorro y Términos
                </h4>
                <p className="text-xs">
                  Los productos de Amazon y Mercado Libre se aprueban automáticamente si cumplen el <strong>Ahorro Mínimo en Pesos ($)</strong> configurado en esta página. Si un producto contiene palabras de la lista de términos excluidos, se descarta automáticamente.
                </p>
              </div>

              <div>
                <h4 className="font-bold text-on-surface text-sm mb-1.5 flex items-center gap-2">
                  <span className="material-symbols-outlined text-xs text-primary">sync</span>
                  Sincronización Dual (Syncthing)
                </h4>
                <p className="text-xs">
                  Cualquier ajuste realizado en este panel se sincroniza automáticamente con el entorno de Linux.
                </p>
              </div>
            </div>

            <div className="p-4 border-t border-outline-variant/50 flex justify-end">
              <button 
                onClick={() => setShowUserGuide(false)}
                className="px-5 py-2 bg-primary text-on-primary text-xs font-label-caps uppercase rounded-lg hover:brightness-110 transition-all cursor-pointer"
              >
                Entendido
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

