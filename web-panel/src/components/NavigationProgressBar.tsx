'use client';
import { useEffect, useState, useRef } from 'react';
import { usePathname } from 'next/navigation';

export default function NavigationProgressBar() {
  const pathname = usePathname();
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const fallbackTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Cuando el pathname cambia, la navegación terminó con éxito
  useEffect(() => {
    if (visible) {
      setProgress(100);
      const timer = setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, 250);
      if (fallbackTimerRef.current) {
        clearTimeout(fallbackTimerRef.current);
        fallbackTimerRef.current = null;
      }
      return () => clearTimeout(timer);
    }
  }, [pathname]);

  // Interceptar clics en enlaces internos para iniciar la barra de progreso de inmediato
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement)?.closest('a');
      if (!target) return;

      const href = target.getAttribute('href');
      // Solo para rutas internas que no sean anclas (#) ni logout
      if (
        href &&
        href.startsWith('/') &&
        !href.startsWith('/auth') &&
        !href.startsWith('#') &&
        href !== pathname
      ) {
        setVisible(true);
        setProgress(25);
        setTimeout(() => setProgress(65), 150);
        setTimeout(() => setProgress(85), 400);

        // Fallback de seguridad: Si tras 2.5 segundos Next.js no ha cambiado de ruta
        // (por ejemplo por router congelado o caché rota), forzar la navegación directa
        if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
        fallbackTimerRef.current = setTimeout(() => {
          if (window.location.pathname !== href) {
            window.location.href = href;
          }
        }, 2500);
      }
    };

    document.addEventListener('click', handleClick);
    return () => {
      document.removeEventListener('click', handleClick);
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    };
  }, [pathname]);

  if (!visible && progress === 0) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] pointer-events-none h-[3px] bg-transparent">
      <div
        className="h-full bg-gradient-to-r from-primary via-primary-container to-cyan-300 shadow-[0_0_10px_#38bdf8] transition-all duration-200 ease-out"
        style={{
          width: `${progress}%`,
          opacity: visible ? 1 : 0,
          transitionProperty: 'width, opacity',
        }}
      />
    </div>
  );
}
