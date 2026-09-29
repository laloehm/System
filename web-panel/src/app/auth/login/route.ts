import { NextRequest, NextResponse } from 'next/server';

const SESSION_COOKIE = 'panel_session';
const DEFAULT_KEY = 'gangas2026';

export async function POST(request: NextRequest) {
  const envKey = (process.env.PANEL_API_KEY || '').trim();
  const panelKey = envKey || DEFAULT_KEY;
  const body = await request.json().catch(() => ({}));
  const key = typeof body?.key === 'string' ? body.key.trim() : '';

  // Permite la clave configurada O la clave por defecto 'gangas2026'
  if (key !== panelKey && key !== DEFAULT_KEY && key !== 'gangas2026') {
    return NextResponse.json({ detail: 'Clave incorrecta' }, { status: 401 });
  }

  const proto = request.headers.get('x-forwarded-proto') || request.nextUrl.protocol.replace(':', '');
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, panelKey, {
    httpOnly: true,
    secure: proto === 'https',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 365, // 1 año de sesión activa
  });
  return res;
}
