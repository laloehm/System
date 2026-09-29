import { NextRequest, NextResponse } from 'next/server';

function clearSession(res: NextResponse) {
  res.cookies.set('panel_session', '', { path: '/', maxAge: 0 });
  return res;
}

export async function POST() {
  return clearSession(NextResponse.json({ ok: true }));
}

export async function GET(request: NextRequest) {
  return clearSession(NextResponse.redirect(new URL('/login', request.url)));
}
