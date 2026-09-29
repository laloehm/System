'use client';
import { useState, useEffect } from 'react';
import { useToast } from '@/components/ui/Toast';

export default function Dashboard() {
  const [mounted, setMounted] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);
  const [activeNetworks, setActiveNetworks] = useState<Record<string, boolean> | null>(null);
  const [schedulerConfig, setSchedulerConfig] = useState<any>(null);
  const [dashboard, setDashboard] = useState<any>(null);
  const [resources, setResources] = useState<any>(null);
  const { success, error, toast } = useToast();

  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    setMounted(true);
    const fetchState = async () => {
      try {
        const [stateRes, schedRes, dashRes] = await Promise.all([
          apiFetch('/api/config/state'),
          apiFetch('/api/config/scheduler'),
          apiFetch('/api/dashboard'),
        ]);
        if (stateRes.ok) {
          const data = await stateRes.json();
          if (data && data.active_networks) {
            setActiveNetworks(data.active_networks);
          }
        }
        if (schedRes.ok) {
          const sData = await schedRes.json();
          setSchedulerConfig(sData.scheduler || sData);
        }
        if (dashRes.ok) {
          const dData = await dashRes.json();
          setDashboard(dData);
        }
      } catch (e) {
        console.error("Error fetching state or schedule:", e);
      }
    };
    const fetchResources = async () => {
      try {
        const res = await apiFetch('/api/system/resources');
        if (res.ok) {
          setResources(await res.json());
        }
      } catch (e) {
        console.error("Error fetching resources:", e);
      }
    };
    fetchState();
    fetchResources();
    const interval = setInterval(fetchState, 10000);
    const resInterval = setInterval(fetchResources, 30000);
    return () => { clearInterval(interval); clearInterval(resInterval); };
  }, []);

  const handlePublish = async (network: string) => {
    setPublishing(network);
    try {
      const res = await apiFetch(`/api/bot/publish/${network}`, { method: 'POST' });
      if (res.ok) {
        success(`Publicación en ${network.toUpperCase()} iniciada.`);
      } else {
        error(`Error al publicar en ${network}`);
      }
    } catch (e) {
      error('Error de conexión');
    }
    setPublishing(null);
  };

  const nicheLabels: Record<string, string> = {
    general: 'General',
    bebes: 'Bebés',
    mascotas: 'Mascotas',
    tenis: 'Tenis',
    moda: 'Moda',
  };

  const queues = dashboard?.queues;
  const fbGroups = dashboard?.fb_groups;
  const lastPub = dashboard?.last_published;
  const videoMode = dashboard?.video_mode || 'normal';

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto pb-24 animate-in fade-in duration-500">
      
      {/* BEGIN: SystemHeader */}
      <section className="flex items-start gap-3" data-purpose="system-header">
        <div className="bg-primary/10 p-2 rounded-lg">
          <span className="material-symbols-outlined text-primary">analytics</span>
        </div>
        <div>
          <h2 className="text-xl md:text-2xl font-bold text-on-surface">Estado del Sistema</h2>
          <p className="text-on-surface-variant text-sm flex items-center gap-1 mt-1">
            <span className="material-symbols-outlined text-[16px]">calendar_today</span>
            {mounted ? new Date().toLocaleString('es-MX') : 'Cargando...'}
          </p>
        </div>
      </section>
      {/* END: SystemHeader */}

      {/* BEGIN: NetworksSection */}
      <section className="bg-surface-container rounded-xl p-4 md:p-5 border border-outline-variant" data-purpose="networks-status">
        <div className="flex items-center gap-2 mb-4 text-primary">
          <span className="material-symbols-outlined text-[20px]">language</span>
          <span className="font-label-caps text-[12px] uppercase tracking-widest">Redes Activas</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {activeNetworks ? (
            [
              { key: 'facebook', label: 'FB Grupos Gen' },
              { key: 'facebook_bebes', label: 'FB Bebés' },
              { key: 'facebook_pets', label: 'FB Mascotas' },
              { key: 'facebook_moda', label: 'FB Moda' },
              { key: 'facebook_tenis', label: 'FB Tenis' },
              { key: 'fb_page', label: 'FB Page' },
              { key: 'telegram', label: 'Telegram' },
              { key: 'twitter', label: 'Twitter / X' },
              { key: 'pinterest', label: 'Pinterest' },
              { key: 'tiktok', label: 'TikTok' },
              { key: 'youtube', label: 'YouTube' },
              { key: 'web', label: 'WordPress' },
            ].map((net) => {
              const isOn = activeNetworks[net.key];
              return (
                <div key={net.key} className={`flex items-center gap-1 bg-surface-container-low px-2 py-1.5 rounded-md border ${isOn ? 'border-emerald-500/30' : 'border-rose-500/30'}`}>
                  <span className={`material-symbols-outlined text-[16px] ${isOn ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isOn ? 'check_circle' : 'cancel'}
                  </span>
                  <span className="text-xs font-medium text-on-surface">{net.label}</span>
                </div>
              );
            })
          ) : (
            <div className="text-sm text-on-surface-variant animate-pulse">Cargando estado de redes...</div>
          )}
        </div>
      </section>
      {/* END: NetworksSection */}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* BEGIN: Left Column (Queues, FB Groups, Alerts) */}
        <div className="space-y-6">
          
          <div className="grid grid-cols-2 gap-4">
            {/* Queue Status */}
            <section className="bg-surface-container rounded-xl p-4 border border-outline-variant hover:border-primary/30 transition-colors" data-purpose="queue-status">
              <div className="flex items-center gap-2 mb-3 text-primary">
                <span className="material-symbols-outlined text-[20px]">assignment</span>
                <span className="font-label-caps text-[10px] uppercase tracking-widest">Colas</span>
              </div>
              <div className="mb-3">
                <span className="text-2xl font-bold text-on-surface">{queues?.total ?? '—'}</span> <span className="text-on-surface-variant text-xs uppercase tracking-wider">en espera</span>
              </div>
              <div className="space-y-1.5 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-outline-variant/50 ml-1">
                {queues?.by_niche?.map((q: any) => (
                  <div key={q.niche} className="text-sm text-on-surface-variant flex justify-between relative pl-6 before:absolute before:left-1 before:top-1/2 before:-translate-y-1/2 before:w-3 before:h-px before:bg-outline-variant/50">
                    <span>{nicheLabels[q.niche] || q.niche}</span> <span className="text-on-surface font-medium">{q.count}</span>
                  </div>
                )) ?? (
                  <div className="text-sm text-on-surface-variant animate-pulse">Cargando...</div>
                )}
              </div>
            </section>

            {/* Facebook Groups */}
            <section className="bg-surface-container rounded-xl p-4 border border-outline-variant hover:border-primary/30 transition-colors" data-purpose="fb-groups">
              <div className="flex items-center gap-2 mb-3 text-primary">
                <span className="material-symbols-outlined text-[20px]">groups</span>
                <span className="font-label-caps text-[10px] uppercase tracking-widest">FB Grupos</span>
              </div>
              <div className="mb-3 flex items-baseline gap-2">
                <div><span className="text-2xl font-bold text-on-surface">{fbGroups?.total ?? '—'}</span> <span className="text-on-surface-variant text-xs uppercase tracking-wider">activos</span></div>
                {fbGroups?.total_paused > 0 && (
                  <div className="text-rose-400 text-sm font-medium">({fbGroups.total_paused} pausados)</div>
                )}
              </div>
              <div className="space-y-1.5 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-outline-variant/50 ml-1">
                {fbGroups?.by_niche ? (
                  Object.entries(fbGroups.by_niche).map(([niche, data]: [string, any]) => {
                    const active = typeof data === 'object' ? data.active : data;
                    const paused = typeof data === 'object' ? data.paused : 0;
                    return (
                      <div key={niche} className="text-sm text-on-surface-variant flex justify-between relative pl-6 before:absolute before:left-1 before:top-1/2 before:-translate-y-1/2 before:w-3 before:h-px before:bg-outline-variant/50">
                        <span>{nicheLabels[niche] || niche}</span> 
                        <span className="text-on-surface font-medium">
                          {active} {paused > 0 && <span className="text-rose-400 text-xs ml-1">({paused}p)</span>}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <div className="text-sm text-on-surface-variant animate-pulse">Cargando...</div>
                )}
              </div>
            </section>
          </div>

          {/* Failures And Last Published */}
          <section className="space-y-3" data-purpose="alerts-summary">
            <div className="bg-surface-container rounded-xl p-4 border border-outline-variant group hover:border-primary/30 transition-colors cursor-pointer">
              <div className="flex items-center gap-2 mb-3 text-primary">
                <span className="material-symbols-outlined text-[20px]">package</span>
                <span className="font-label-caps text-[12px] uppercase tracking-widest">Último publicado</span>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-on-surface group-hover:text-primary transition-colors">
                    {lastPub?.title || lastPub?.product_id || 'Sin datos'}
                  </p>
                  <p className="text-xs text-on-surface-variant mt-0.5">
                    {lastPub?.timestamp
                      ? `Publicado ${new Date(lastPub.timestamp).toLocaleString('es-MX')}`
                      : lastPub?.published_at
                        ? `Publicado ${new Date(lastPub.published_at).toLocaleString('es-MX')}`
                        : 'Sin fecha'}
                  </p>
                </div>
                <span className="material-symbols-outlined text-on-surface-variant group-hover:translate-x-1 transition-transform">chevron_right</span>
              </div>
            </div>

            <div className="bg-surface-container-low rounded-xl p-3 flex items-center justify-between border border-outline-variant">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[20px] text-on-surface-variant">movie</span>
                <span className="text-sm text-on-surface-variant">Modo video</span>
              </div>
              <span className="text-sm font-bold text-primary capitalize">{videoMode}</span>
            </div>
          </section>
          
        </div>
        {/* END: Left Column */}

        {/* BEGIN: Right Column (Schedules, Server Resources) */}
        <div className="space-y-6">
          
          {/* ScheduledTimes */}
          <section className="bg-surface-container rounded-xl p-4 md:p-5 border border-outline-variant" data-purpose="scheduling">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-primary">
                <span className="material-symbols-outlined text-[20px]">schedule</span>
                <span className="font-label-caps text-[12px] uppercase tracking-widest">Horarios</span>
              </div>
              <span className="font-status-indicator text-[10px] text-primary bg-primary/10 px-2 py-0.5 rounded border border-primary/20">[ACTIVE]</span>
            </div>
            
            <div className="grid grid-cols-4 gap-2 mb-5">
              {(() => {
                const hours = schedulerConfig?.general || [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
                const currentHour = new Date().getHours();
                const nextHour = hours.find((h: number) => h > currentHour) || hours[0];

                return hours.map((hour: number) => {
                  const isNext = hour === nextHour;
                  return (
                    <div key={hour} className={`text-center py-1.5 px-1 rounded font-label-caps text-[11px] ${
                      isNext 
                        ? 'bg-primary/20 text-primary font-bold border border-primary/40' 
                        : 'bg-surface-container-high text-on-surface-variant border border-transparent'
                    }`}>
                      {hour.toString().padStart(2, '0')}:00
                    </div>
                  );
                });
              })()}
            </div>
            
            <div className="flex items-center gap-2 text-primary font-medium animate-pulse bg-surface-container-low p-3 rounded-lg border border-primary/20">
              <span className="material-symbols-outlined text-[18px]">forward</span>
              <span className="text-xs uppercase font-label-caps tracking-wider">
                Próxima: <span className="font-bold">
                  {(() => {
                    const hours = schedulerConfig?.general || [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22];
                    const currentHour = new Date().getHours();
                    const nextHour = hours.find((h: number) => h > currentHour) || hours[0];
                    return `${nextHour.toString().padStart(2, '0')}:00`;
                  })()}
                </span>
              </span>
            </div>
          </section>

          {/* ServerResources */}
          <section className="bg-surface-container rounded-xl p-4 md:p-5 border border-outline-variant" data-purpose="server-resources">
            <div className="flex items-center gap-2 mb-5 text-primary">
              <span className="material-symbols-outlined text-[20px]">memory</span>
              <span className="font-label-caps text-[12px] uppercase tracking-widest">Servidor</span>
            </div>
            
            <div className="space-y-5">
              {/* CPU */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-on-surface">
                  <span className="flex items-center gap-1.5"><span className="material-symbols-outlined text-[16px] text-on-surface-variant">bolt</span> CPU</span>
                  <span className="font-bold font-label-caps">{resources ? `${resources.cpu_percent}%` : '—'}</span>
                </div>
                <div className="w-full bg-surface-container-highest rounded-full h-2 overflow-hidden shadow-inner">
                  <div className="bg-primary h-full rounded-full transition-all duration-1000 ease-in-out" style={{ width: `${resources?.cpu_percent ?? 0}%` }}></div>
                </div>
              </div>
              
              {/* RAM */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-on-surface">
                  <span className="flex items-center gap-1.5"><span className="material-symbols-outlined text-[16px] text-on-surface-variant">psychology</span> RAM</span>
                  <span className="font-bold font-label-caps">{resources ? `${resources.ram_percent}%` : '—'} <span className="text-on-surface-variant font-normal tracking-wide ml-1">({resources ? `${resources.ram_used_gb} / ${resources.ram_total_gb} GB` : ''})</span></span>
                </div>
                <div className="w-full bg-surface-container-highest rounded-full h-2 overflow-hidden shadow-inner">
                  <div className="bg-emerald-400 h-full rounded-full transition-all duration-1000 ease-in-out" style={{ width: `${resources?.ram_percent ?? 0}%` }}></div>
                </div>
              </div>
              
              {/* Disk */}
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-on-surface">
                  <span className="flex items-center gap-1.5"><span className="material-symbols-outlined text-[16px] text-on-surface-variant">database</span> Disco</span>
                  <span className="font-bold font-label-caps">{resources ? `${resources.disk_percent}%` : '—'} <span className="text-on-surface-variant font-normal tracking-wide ml-1">({resources ? `${resources.disk_used_gb} / ${resources.disk_total_gb} GB` : ''})</span></span>
                </div>
                <div className="w-full bg-surface-container-highest rounded-full h-2 overflow-hidden shadow-inner">
                  <div className="bg-amber-400 h-full rounded-full transition-all duration-1000 ease-in-out" style={{ width: `${resources?.disk_percent ?? 0}%` }}></div>
                </div>
              </div>
            </div>
          </section>

        </div>
        {/* END: Right Column */}
      </div>



    </div>
  );
}
