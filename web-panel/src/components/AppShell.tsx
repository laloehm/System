'use client';
import { usePathname } from 'next/navigation';
import TopAppBar from '@/components/TopAppBar';
import Sidebar from '@/components/Sidebar';
import BottomNav from '@/components/BottomNav';
import NavigationProgressBar from '@/components/NavigationProgressBar';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === '/login' || pathname?.startsWith('/login/');

  return (
    <>
      <NavigationProgressBar />
      {!isLoginPage && <TopAppBar />}
      <div className="flex min-h-screen">
        {!isLoginPage && <Sidebar />}
        <main className={`flex-1 overflow-x-hidden bg-background ${isLoginPage ? 'p-4 md:p-8 flex items-center justify-center min-h-screen' : 'px-0 md:p-margin-desktop pb-32'}`}>
          <div className={isLoginPage ? 'w-full max-w-4xl mx-auto' : 'w-full md:max-w-5xl md:mx-auto'}>
            {children}
          </div>
        </main>
      </div>
      {!isLoginPage && <BottomNav />}
    </>
  );
}
