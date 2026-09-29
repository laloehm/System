import fs from 'fs';
import path from 'path';
import Link from 'next/link';
import ClientActions from './ClientActions';

export default async function LastPublishedPage() {
  let data: any = null;
  try {
    const filePath = path.join(process.cwd(), '../last_published.json');
    const fileContent = fs.readFileSync(filePath, 'utf-8');
    data = JSON.parse(fileContent);
  } catch (e) {
    console.error("Error reading last_published.json:", e);
  }

  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center gap-4">
        <span className="material-symbols-outlined text-5xl text-on-surface-variant opacity-40">history</span>
        <h2 className="text-base font-bold text-on-surface">Nada publicado aún</h2>
        <p className="text-sm text-on-surface-variant max-w-xs">No se encontró historial de publicaciones recientes.</p>
        <Link href="/publish" className="mt-2 px-5 py-2.5 bg-surface-container-high rounded-lg text-xs font-label-caps text-on-surface border border-outline-variant">
          Volver
        </Link>
      </div>
    );
  }

  const parsePrice = (str: any) => {
    if (!str) return 0;
    let s = String(str).replace(/\$/g, '').trim();
    if (/,\d{1,2}$/.test(s)) {
      s = s.replace(/,(\d{1,2})$/, '.$1');
    }
    s = s.replace(/,/g, '').replace(/[^0-9.]/g, '');
    return parseFloat(s) || 0;
  };
  const offer = parsePrice(data.offer_price);
  const list  = parsePrice(data.list_price);
  const saving = list > offer && list > 0 ? `$${(list - offer).toFixed(0)}` : '—';

  return (
    <div className="w-full overflow-x-hidden pb-24">

      {/* ── HERO IMAGE ── */}
      <div className="w-full h-44 md:h-64 bg-white relative overflow-hidden border-b border-outline-variant">
        {data.image_url ? (
          <img
            src={data.image_url}
            alt={data.title || 'Producto'}
            className="absolute inset-0 w-full h-full object-contain p-3"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-container">
            <span className="material-symbols-outlined text-5xl text-on-surface-variant opacity-30">image</span>
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-surface/60 pointer-events-none" />
      </div>

      {/* ── PRODUCT INFO ── */}
      <div className="px-4 pt-4 space-y-3">

        {/* Time badge */}
        <div className="flex items-center gap-2 w-fit px-2.5 py-1 bg-surface-container-high rounded-md border border-outline-variant">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          <span className="text-[10px] font-label-caps text-on-surface tracking-widest uppercase">
            Publicado a las {data.published_at || '—'}
          </span>
        </div>

        {/* Title */}
        <h1 className="text-sm font-bold text-on-surface leading-snug line-clamp-3">
          {data.title || 'Sin título'}
        </h1>

        {/* Price row — horizontal flex, no grid overlap */}
        <div className="flex items-stretch gap-0 bg-surface-container-low rounded-xl border border-outline-variant overflow-hidden">
          <div className="flex-1 flex flex-col items-center justify-center py-3 px-2 border-r border-outline-variant/50">
            <span className="text-[9px] text-on-surface-variant font-label-caps uppercase tracking-wider mb-0.5">Oferta</span>
            <span className="text-primary font-bold text-base leading-none">{data.offer_price || '—'}</span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center py-3 px-2 border-r border-outline-variant/50">
            <span className="text-[9px] text-on-surface-variant font-label-caps uppercase tracking-wider mb-0.5">Antes</span>
            <span className="text-outline line-through text-sm leading-none">{data.list_price || '—'}</span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center py-3 px-2 border-r border-outline-variant/50">
            <span className="text-[9px] text-on-surface-variant font-label-caps uppercase tracking-wider mb-0.5">Dcto</span>
            <span className="text-primary font-bold text-sm leading-none">{data.discount || '—'}</span>
          </div>
          <div className="flex-1 flex flex-col items-center justify-center py-3 px-2">
            <span className="text-[9px] text-on-surface-variant font-label-caps uppercase tracking-wider mb-0.5">Ahorro</span>
            <span className="text-on-surface font-medium text-sm leading-none">{saving}</span>
          </div>
        </div>
      </div>

      {/* ── PRIMARY LINKS ── */}
      <div className="px-4 pt-4 grid grid-cols-2 gap-2">
        <a
          href={data.affiliate_url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 py-3 bg-surface-container-high text-on-surface text-[11px] font-label-caps rounded-lg border border-outline-variant active:scale-[0.97] transition-all"
        >
          <span className="material-symbols-outlined text-[16px] text-primary">link</span>
          Afiliado
        </a>
        <a
          href={data.real_url || data.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 py-3 bg-surface-container-high text-on-surface text-[11px] font-label-caps rounded-lg border border-outline-variant active:scale-[0.97] transition-all"
        >
          <span className="material-symbols-outlined text-[16px] text-primary">open_in_new</span>
          Original
        </a>
      </div>

      {/* ── ACTION BUTTONS (client) ── */}
      <div className="px-4 pt-3 space-y-2">
        <ClientActions productId={String(data.id || data.product_id || '')} />
      </div>

      {/* ── BACK BUTTON ── */}
      <div className="px-4 pt-4">
        <Link
          href="/publish"
          className="w-full flex items-center justify-center gap-2 py-3.5 bg-surface-container border border-primary/20 text-primary text-[11px] font-label-caps rounded-xl active:scale-[0.98] transition-all"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          Volver al listado
        </Link>
      </div>

    </div>
  );
}
