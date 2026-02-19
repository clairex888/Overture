'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Loader2, Activity } from 'lucide-react';
import { useAuth } from '@/components/providers/AuthProvider';
import Sidebar from '@/components/layout/Sidebar';

const PUBLIC_PATHS = ['/login'];

export default function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (!loading && !user && !isPublicPath) {
      router.replace('/login');
    }
    if (!loading && user && isPublicPath) {
      router.replace('/');
    }
  }, [loading, user, isPublicPath, router]);

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-dark-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-info to-accent flex items-center justify-center">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <Loader2 className="w-5 h-5 text-info animate-spin" />
        </div>
      </div>
    );
  }

  // Public pages (login) — render without sidebar
  if (isPublicPath) {
    return <>{children}</>;
  }

  // Not authenticated — show nothing (redirect in progress)
  if (!user) {
    return null;
  }

  // Authenticated — full layout with sidebar
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-60">
        <div className="p-6 max-w-[1600px]">{children}</div>
      </main>
    </div>
  );
}
