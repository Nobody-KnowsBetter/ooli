'use client';

import { useEffect, useState } from 'react';
import { AuthContext } from '@/components/AuthContext';
import { LoginSetupBanner } from '@/components/LoginSetupBanner';
import { Sidebar } from '@/components/Sidebar';
import { AuthStatus, getAuthStatus } from '@/lib/api';

// Only the landing page has sign-in, so anyone signed out, or whose session ended, returns there.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    const check = () =>
      getAuthStatus()
        .then((status) => {
          if (status.login_enabled && !status.logged_in) {
            window.location.replace('/');
            return;
          }
          setAuth(status);
          setBackendDown(false);
        })
        .catch(() => setBackendDown(true));

    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, []);

  if (backendDown) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6 text-sm text-zinc-600">
        The DocGuard backend isn&apos;t reachable. Start it, then reload this page.
      </main>
    );
  }

  if (!auth) {
    return <main className="min-h-screen flex items-center justify-center text-sm text-zinc-500">Loading...</main>;
  }

  return (
    <AuthContext.Provider value={auth}>
      <div className="flex min-h-screen">
        <Sidebar auth={auth} />
        <div className="flex-1 flex flex-col min-w-0">
          {!auth.login_enabled && <LoginSetupBanner />}
          {children}
        </div>
      </div>
    </AuthContext.Provider>
  );
}
