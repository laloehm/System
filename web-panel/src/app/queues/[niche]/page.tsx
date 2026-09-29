import fs from 'fs';
import path from 'path';
import QueueClient from './components/QueueClient';

async function getQueueData(niche: string) {
  const url = `http://127.0.0.1:8001/api/queues/${niche}`;
  try {
    const res = await fetch(url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(1500),
      headers: { 'x-panel-key': process.env.PANEL_API_KEY || 'gangas2026' },
    });
    if (res.ok) {
      const data = await res.json();
      return { products: data.products || [] };
    }
  } catch (e) {
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
    const filename = queueFiles[niche.toLowerCase()] || 'products_list.json';
    const filePath = path.join(baseDir, filename);
    const historyPath = path.join(baseDir, 'published_history.json');

    let history = new Set<string>();
    if (fs.existsSync(historyPath)) {
      const histData = JSON.parse(fs.readFileSync(historyPath, 'utf-8'));
      if (Array.isArray(histData)) {
        history = new Set(histData.map((id: any) => String(id)));
      }
    }

    if (fs.existsSync(filePath)) {
      const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      if (Array.isArray(data)) {
        const pending = data.filter((p: any) => 
          p.force_publish || (!history.has(String(p.id)) && !history.has(p.affiliate_url))
        );
        return { products: pending };
      }
    }
  } catch (err) {
    console.error(err);
  }
  return { products: [] };
}

export default async function QueuePage({ params }: { params: Promise<{ niche: string }> | { niche: string } }) {
  // Support Next 14 and 15 safely
  const resolvedParams = await Promise.resolve(params);
  const niche = resolvedParams.niche;
  const { products } = await getQueueData(niche);

  return <QueueClient niche={niche} initialProducts={products} />;
}
