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
  ExternalLink,
  History,
} from 'lucide-react';
import { GithubIcon } from '@/components/GithubIcon';
import { getHealth, getRepositories, getSelectedRepo, Health } from '@/lib/api';

const navigation = [
  { name: 'Overview', href: '/', icon: LayoutDashboard },
  { name: 'Repositories', href: '/repositories', icon: GitBranch },
  { name: 'Issues', href: '/issues', icon: AlertTriangle },
  { name: 'Auto-Fix', href: '/autofix', icon: Wand2 },
  { name: 'History', href: '/history', icon: History },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [repoName, setRepoName] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [repos, status] = await Promise.all([getRepositories(), getHealth()]);
        const selected = getSelectedRepo();
        setRepoName(repos.find((r) => r.id === selected)?.full_name ?? repos[0]?.full_name ?? null);
        setHealth(status);
        setBackendDown(false);
      } catch {
        setBackendDown(true);
      }
    };
    load();
    // Keeps the status true if Ollama or the backend stops, or another repository is picked.
    const timer = setInterval(load, 15000);
    window.addEventListener('docguard-repo-changed', load);
    return () => {
      clearInterval(timer);
      window.removeEventListener('docguard-repo-changed', load);
    };
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
    red: 'text-red-400',
    zinc: 'text-zinc-400',
    emerald: 'text-emerald-400',
    amber: 'text-amber-400',
  };

  return (
    <aside className="w-64 bg-card border-r border-border flex flex-col justify-between shrink-0 h-screen sticky top-0">
      <div className="flex flex-col">
        {/* Brand Header */}
        <div className="h-14 px-5 flex items-center justify-between border-b border-border">
          <Link href="/" className="flex items-center space-x-2.5 group">
            <div className="h-7 w-7 rounded-md bg-white text-black flex items-center justify-center font-bold shadow-sm">
              <ShieldCheck className="w-4 h-4 stroke-[2.5]" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight text-white block">DocGuard</span>
            </div>
          </Link>
          <span className="text-[10px] px-2 py-0.5 rounded border border-border text-zinc-400 font-mono">
            v1.0
          </span>
        </div>

        {/* Repository context */}
        <div className="px-4 py-2.5 border-b border-border bg-black/40">
          <div className="flex items-center space-x-2 text-xs text-zinc-400">
            <GithubIcon className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
            <span className="truncate font-mono text-[11px] text-zinc-300">
              {repoName ?? 'No repository'}
            </span>
          </div>
          <div className={`flex items-center space-x-1.5 mt-1 text-[11px] font-mono ${textColor[engineStatus.color]}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${dotColor[engineStatus.color]}`}></span>
            <span>{engineStatus.label}</span>
          </div>
        </div>

        {/* Nav Links */}
        <nav className="p-2.5 space-y-1">
          {navigation.map((item) => {
            const isActive =
              item.href === '/'
                ? pathname === '/'
                : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center space-x-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-zinc-800 text-white font-semibold border border-zinc-700/80 shadow-sm'
                    : 'text-zinc-400 hover:text-white hover:bg-card-hover'
                }`}
              >
                <Icon
                  className={`w-4 h-4 ${
                    isActive ? 'text-white' : 'text-zinc-400'
                  }`}
                />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-border">
        <a
          href={repoName ? `https://github.com/${repoName}` : 'https://github.com'}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between text-xs text-zinc-400 hover:text-white p-2 rounded-md hover:bg-card-hover transition"
        >
          <span className="flex items-center space-x-2">
            <GithubIcon className="w-3.5 h-3.5" />
            <span>GitHub Repository</span>
          </span>
          <ExternalLink className="w-3.5 h-3.5 text-zinc-500" />
        </a>
      </div>
    </aside>
  );
}
