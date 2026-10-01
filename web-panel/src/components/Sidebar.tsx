'use client';
import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { icon: 'home', label: 'Inicio', href: '/' },
    { icon: 'inventory_2', label: 'Contenido', href: '/queues' },
    { icon: 'hub', label: 'Redes', href: '/networks' },
    { icon: 'send', label: 'Publicación', href: '/publish' },
    { icon: 'schedule', label: 'Programación', href: '/scheduler' },
    { icon: 'history', label: 'Historial', href: '/history' },
    { icon: 'delete_sweep', label: 'Descartados', href: '/discarded' },
    { icon: 'settings', label: 'Ajustes', href: '/settings' },
  ];

  return (
    <aside className="hidden md:flex flex-col p-md gap-base h-full w-64 sticky top-16 bg-surface-container-lowest border-r border-outline-variant">
      <div className="py-md px-sm">
        <span className="font-label-caps text-label-caps text-on-surface-variant">DIRECTORIO</span>
      </div>
      <nav className="flex flex-col gap-base">
        {navItems.map((item) => {
          const isActive = pathname ? (pathname === item.href || pathname.startsWith(item.href + '/') && item.href !== '/') : false;
          
          return (
            <Link 
              key={item.href}
              href={item.href}
              prefetch={false}
              className={`flex items-center gap-md p-md transition-all duration-200 rounded-lg ${
                isActive 
                  ? 'text-primary-container font-bold bg-secondary-container/50' 
                  : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'
              }`}
            >
              <span className="material-symbols-outlined" style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}>
                {item.icon}
              </span>
              <span className="font-body-sm">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
