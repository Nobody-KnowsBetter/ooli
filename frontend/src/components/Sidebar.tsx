'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  GitBranch,
  AlertTriangle,
  Wand2,
  Settings,
  ShieldCheck,
  History,
  LogOut,
} from 'lucide-react';
import { AuthStatus, getHealth, Health, logout } from '@/lib/api';

const navigation = [
  { name: 'Overview', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Repositories', href: '/dashboard/repositories', icon: GitBranch },
  { name: 'Issues', href: '/dashboard/issues', icon: AlertTriangle },
  { name: 'Fixes', href: '/dashboard/autofix', icon: Wand2 },
  { name: 'History', href: '/dashboard/history', icon: History },
  { name: 'Settings', href: '/dashboard/settings', icon: Settings },
];

export function Sidebar({ auth }: { auth: AuthStatus }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        setHealth(await getHealth());
        setBackendDown(false);
      } catch {
        setBackendDown(true);
      }
    };
    load();
    // Keeps the status true if the model or the backend stops.
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const usingModel = health?.ai_provider === 'qwen' && health?.model_ready;
  const engineStatus = backendDown
    ? { label: 'Backend offline', color: 'red' }
    : !health
    ? { label: 'Checking...', color: 'zinc' }
    : usingModel
    ? { label: `${health.model} ready`, color: 'emerald' }
    : health.ai_provider === 'qwen'
    ? { label: 'Qwen offline: using rules', color: 'amber' }
    : { label: 'Rules only (no model)', color: 'zinc' };
  const dotColor: Record<string, string> = {
    red: 'bg-red-400',
    zinc: 'bg-zinc-400',
    emerald: 'bg-emerald-400',
    amber: 'bg-amber-400',
  };
  const textColor: Record<string, string> = {
    red: 'text-red-700',
    zinc: 'text-zinc-600',
    emerald: 'text-emerald-700',
    amber: 'text-amber-700',
  };

  return (
    <aside className="w-64 bg-card border-r border-border flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div className="flex flex-col">
        {/* Brand Header */}
        <div className="h-14 px-5 flex items-center justify-between border-b border-border">
          <a href="/" className="flex items-center space-x-2.5 group">
            <div className="h-7 w-7 rounded-xl bg-ink text-white flex items-center justify-center font-bold">
              <ShieldCheck className="w-4 h-4 stroke-[2.5]" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight text-ink block">DocGuard</span>
            </div>
          </a>
          
        </div>

        {/* Engine status */}
        <div className="px-4 py-2.5 border-b border-border bg-paper">
          <div className={`flex items-center space-x-1.5 text-[11px] ${textColor[engineStatus.color]}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${dotColor[engineStatus.color]}`}></span>
            <span>{engineStatus.label}</span>
          </div>
        </div>

        {/* Nav Links */}
        <nav className="p-2.5 space-y-1">
          {navigation.map((item) => {
            const isActive =
              item.href === '/dashboard'
                ? pathname === '/dashboard'
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-zinc-100 text-ink font-semibold border border-zinc-200 shadow-sm'
                    : 'text-zinc-600 hover:text-ink hover:bg-card-hover'
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    isActive ? 'text-ink' : 'text-zinc-600'
                  }`}
                />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Signed-in user */}
      {auth.user && (
        <div className="p-3 border-t border-border space-y-2">
          <a
            href={`https://github.com/${auth.user.login}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-card-hover transition min-w-0"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={auth.user.avatar_url} alt="" className="h-8 w-8 rounded-full shrink-0 bg-paper" />
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-ink truncate">{auth.user.name}</span>
              <span className="block text-[11px] text-zinc-600 truncate">@{auth.user.login}</span>
            </span>
          </a>
          <button
            type="button"
            onClick={async () => {
              await logout();
              window.location.assign('/');
            }}
            className="w-full flex items-center justify-center gap-2 text-xs font-medium text-zinc-700 hover:text-ink border border-border hover:border-zinc-400 rounded-xl py-2 transition"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign out</span>
          </button>
        </div>
      )}
    </aside>
  );
}
