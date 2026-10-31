'use client';

import { useState } from 'react';
import { RefreshCw, Check } from 'lucide-react';
import { describeScan, triggerLiveScan } from '@/lib/api';

interface HeaderProps {
  title: string;
  subtitle?: string;
  onScanComplete?: () => void;
}

export function Header({ title, subtitle, onScanComplete }: HeaderProps) {
  const [scanning, setScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanOk, setScanOk] = useState(true);

  const handleScan = async () => {
    try {
      setScanning(true);
      setScanOk(true);
      setScanMessage('Scanning last commit...');
      const result = await triggerLiveScan();
      setScanOk(result.total_drifts === 0);
      setScanMessage(describeScan(result, 'the last commit'));
      if (onScanComplete) {
        onScanComplete();
      }
    } catch (err) {
      setScanOk(false);
      setScanMessage(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
      setTimeout(() => setScanMessage(null), 5000);
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
        {/* Scan Status Toast */}
        {scanMessage && (
          <span
            className={`text-[11px] font-mono px-2.5 py-1 rounded border flex items-center space-x-1.5 ${
              scanOk
                ? 'text-emerald-400 bg-emerald-950/20 border-emerald-500/30'
                : 'text-red-400 bg-red-950/20 border-red-500/30'
            }`}
          >
            {scanOk && <Check className="w-3 h-3" />}
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
          <span>{scanning ? 'Scanning...' : 'Scan Last Commit'}</span>
        </button>
      </div>
    </header>
  );
}
