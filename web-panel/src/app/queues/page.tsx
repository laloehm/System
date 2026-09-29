import Link from 'next/link';
import QueueSettings from './components/QueueSettings';

interface QueueSummary {
  niche: string;
  filename: string;
  count: number;
}

import fs from 'fs';
import path from 'path';

async function getQueues() {
  const url = 'http://127.0.0.1:8001/api/queues';
  try {
    const res = await fetch(url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(1500),
      headers: { 'x-panel-key': process.env.PANEL_API_KEY || 'gangas2026' },
    });
    if (res.ok) {
      const data = await res.json();
      if (data && Array.isArray(data.queues)) {
        return { queues: data.queues as QueueSummary[], error: null };
      }
    }
  } catch (e: any) {
    // Failsafe a lectura directa de disco
  }

  // FAILSAFE DISK FALLBACK
  try {
    let baseDir = process.cwd();
    if (!fs.existsSync(path.join(baseDir, 'products_list.json'))) {
      baseDir = path.resolve(process.cwd(), '..');
    }
    const queueFiles: Record<string, string> = {
      general: 'products_list.json',
      moda: 'queue_moda.json',
      tenis: 'queue_tenis.json',
      bebes: 'products_list_baby.json',
      mascotas: 'products_list_pets.json'
    };
    const historyPath = path.join(baseDir, 'published_history.json');
    let history = new Set<string>();
    if (fs.existsSync(historyPath)) {
      const histData = JSON.parse(fs.readFileSync(historyPath, 'utf-8'));
      if (Array.isArray(histData)) {
        history = new Set(histData.map((id: any) => String(id)));
      }
    }

    const summary: QueueSummary[] = [];
    for (const [niche, filename] of Object.entries(queueFiles)) {
      const filePath = path.join(baseDir, filename);
      let count = 0;
      if (fs.existsSync(filePath)) {
        const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        if (Array.isArray(data)) {
          const pending = data.filter((p: any) => 
            p.force_publish || (!history.has(String(p.id)) && !history.has(p.affiliate_url))
          );
          count = pending.length;
        }
      }
      summary.push({ niche, filename, count });
    }
    return { queues: summary, error: null };
  } catch (err: any) {
    return { queues: [], error: 'Error al leer datos locales' };
  }
}

export default async function QueuesHome() {
  const { queues, error } = await getQueues();

  return (
    <div className="flex-1 max-w-4xl mx-auto w-full p-4 md:p-6 space-y-6 pb-32 md:pb-6 animate-in fade-in duration-500">
      
      {/* Header Card */}
      <div className="bg-surface-container-low border border-outline-variant rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-container/20 rounded-lg">
              <span className="material-symbols-outlined text-primary-container text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                inventory_2
              </span>
            </div>
            <h2 className="text-xl font-headline-md text-on-surface">Contenido</h2>
          </div>
        </div>
        <p className="text-sm font-body-sm text-on-surface-variant mt-2">
          Gestiona el estado y registros operativos del sistema de colas.
        </p>
      </div>

      <QueueSettings />

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-xl p-4 flex items-start gap-3">
          <span className="material-symbols-outlined text-error mt-0.5">warning</span>
          <p className="text-sm font-body-sm text-error">
            No se pudo conectar a la API local (Puerto 8001). Error: {error}
          </p>
        </div>
      )}

      {/* Actions List */}
      <div className="space-y-4">
        
        {queues.length === 0 && !error ? (
          <div className="p-6 border border-dashed border-outline-variant rounded-xl text-center">
            <span className="material-symbols-outlined text-on-surface-variant text-4xl mb-2">inbox</span>
            <p className="font-body-sm text-on-surface-variant">No hay colas configuradas actualmente.</p>
          </div>
        ) : (
          queues.map((q) => (
            <Link 
              href={`/queues/${q.niche}`} 
              key={q.niche}
              className="w-full bg-surface-container hover:bg-surface-container-high border border-outline-variant py-5 px-6 rounded-xl flex items-center justify-between transition-all active:scale-[0.98] group"
            >
              <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-on-surface-variant group-hover:text-primary-container transition-colors">
                  folder_open
                </span>
                <span className="text-sm font-label-caps uppercase text-on-surface group-hover:text-primary-container transition-colors">
                  Próximos {q.niche}
                </span>
              </div>
              <div className="bg-surface-container-highest px-3 py-1 rounded-full border border-outline-variant/50">
                <span className="text-xs font-bold text-on-surface-variant group-hover:text-on-surface transition-colors">
                  {q.count} ítems
                </span>
              </div>
            </Link>
          ))
        )}

        <div className="h-px bg-outline-variant w-full my-6"></div>

        <Link 
          href="/history"
          className="w-full bg-primary-container/10 hover:bg-primary-container/20 border-2 border-primary-container py-5 px-6 rounded-xl flex items-center justify-center gap-3 transition-all active:scale-[0.98] group"
        >
          <span className="material-symbols-outlined text-primary-container">history</span>
          <span className="text-xs font-label-caps uppercase text-primary-container">Historial de Publicados</span>
        </Link>
        

      </div>
    </div>
  );
}
