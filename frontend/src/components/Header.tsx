'use client';

import { useState } from 'react';
import { RefreshCw, GitBranch, Search, Check } from 'lucide-react';
import { triggerLiveScan } from '@/lib/api';

interface HeaderProps {
  title: string;
  subtitle?: string;
  onScanComplete?: () => void;
}

export function Header({ title, subtitle, onScanComplete }: HeaderProps) {
  const [scanning, setScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);

  const handleScan = async () => {
    try {
      setScanning(true);
      setScanMessage('Auditing repository...');
      await triggerLiveScan('HEAD~1', 'HEAD');
      setScanMessage('Audit passed');
      if (onScanComplete) {
        onScanComplete();
      }
      setTimeout(() => setScanMessage(null), 3000);
    } catch (err) {
      setScanMessage('Audit failed');
      setTimeout(() => setScanMessage(null), 3000);
    } finally {
      setScanning(false);
    }
  };

  return (
    <header className="h-14 border-b border-border bg-card px-6 flex items-center justify-between sticky top-0 z-40">
      {/* Breadcrumbs & Title */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-1.5 text-xs font-mono text-zinc-500">
          <span>docguard</span>
          <span>/</span>
        </div>
        <div>
          <h1 className="text-xs font-semibold text-white tracking-tight uppercase font-mono">
            {title}
          </h1>
          {subtitle && (
            <p className="text-[11px] text-zinc-400 hidden md:block">
              {subtitle}
            </p>
          )}
        </div>
      </div>

      {/* Center/Right controls */}
      <div className="flex items-center space-x-3">
        {/* Branch pill */}
        <div className="hidden sm:flex items-center space-x-1.5 text-[11px] font-mono text-zinc-400 bg-black px-2.5 py-1 rounded border border-border">
          <GitBranch className="w-3 h-3 text-zinc-500" />
          <span>main</span>
        </div>

        {/* Scan Status Toast */}
        {scanMessage && (
          <span className="text-[11px] text-emerald-400 font-mono bg-emerald-950/20 px-2.5 py-1 rounded border border-emerald-500/30 flex items-center space-x-1.5">
            <Check className="w-3 h-3" />
            <span>{scanMessage}</span>
          </span>
        )}

        {/* Trigger Scan Button */}
        <button
          onClick={handleScan}
          disabled={scanning}
          className="flex items-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 active:scale-[0.98] transition-all text-black px-3.5 py-1.5 rounded-md shadow-sm disabled:opacity-50 font-mono"
        >
          <RefreshCw className={`w-3 h-3 ${scanning ? 'animate-spin' : ''}`} />
          <span>{scanning ? 'Auditing...' : 'Run Audit'}</span>
          <span className="hidden sm:inline-block text-[10px] bg-zinc-200 text-zinc-700 px-1 py-0.2 rounded font-sans ml-1">
            ⌘R
          </span>
        </button>
      </div>
    </header>
  );
}
