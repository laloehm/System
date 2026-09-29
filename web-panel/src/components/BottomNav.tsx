'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function BottomNav() {
  const pathname = usePathname();

  const navItems = [
    { icon: 'home', label: 'Inicio', href: '/' },
    { icon: 'inventory_2', label: 'Conte.', href: '/queues' },
    { icon: 'send', label: 'Publicar', href: '/publish' },
    { icon: 'history', label: 'Hist.', href: '/history' },
    { icon: 'delete_sweep', label: 'Desc.', href: '/discarded' },
    { icon: 'settings', label: 'Ajust.', href: '/settings' },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 left-0 w-full flex justify-around items-center py-xs px-margin-mobile bg-surface-container-high z-50 border-t border-outline-variant shadow-lg">
      {navItems.map((item) => {
        const isActive = pathname ? (pathname === item.href || pathname.startsWith(item.href + '/') && item.href !== '/') : false;
        
        return (
          <Link 
            key={item.href} 
            href={item.href}
            prefetch={false}
            className={`flex flex-col items-center justify-center transition-colors duration-150 ${
              isActive 
                ? 'text-primary bg-secondary-container/20 rounded px-4 py-1' 
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <span className="material-symbols-outlined" style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}>
              {item.icon}
            </span>
            <span className="font-label-caps text-[10px] mt-1">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
