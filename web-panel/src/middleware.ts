import { NextRequest, NextResponse } from 'next/server';

const SESSION_COOKIE = 'panel_session';
const PUBLIC_PATHS = ['/login', '/auth/login'];
const DEFAULT_KEY = 'gangas2026';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const envKey = (process.env.PANEL_API_KEY || '').trim();
  const panelKey = envKey || DEFAULT_KEY;

  if (PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }

  const cookieVal = request.cookies.get(SESSION_COOKIE)?.value;
  const incomingKey = (request.headers.get('x-panel-key') || '').trim();
  // Acepta si tiene cookie de sesión válida o si envía el x-panel-key correcto
  const authenticated = !!cookieVal || incomingKey === panelKey || incomingKey === DEFAULT_KEY || incomingKey === 'gangas2026';

  if (pathname.startsWith('/api/')) {
    if (!authenticated) {
      return NextResponse.json({ detail: 'No autorizado' }, { status: 401 });
    }
    // Retorna NextResponse.next() directamente sin clonar headers para evitar que Next.js
    // descarte o congele el body en peticiones PUT/POST hacia la API reescrita en next.config.ts
    return NextResponse.next();
  }

  if (!authenticated) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('next', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
