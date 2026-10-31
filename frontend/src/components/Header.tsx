'use client';

import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Check } from 'lucide-react';
import { isPortal, useAuth } from '@/components/AuthContext';
import { describeScan, getSyncStatus, startSync, SyncStatus, triggerLiveScan } from '@/lib/api';

interface HeaderProps {
  title: string;
  subtitle?: string;
  onScanComplete?: () => void;
}

function timeAgo(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}

export function Header({ title, subtitle, onScanComplete }: HeaderProps) {
  const portal = isPortal(useAuth());
  const [scanning, setScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanOk, setScanOk] = useState(true);
  const [sync, setSync] = useState<SyncStatus | null>(null);
  const lastSynced = useRef<string | null>(null);
  const refreshPage = useRef(onScanComplete);
  refreshPage.current = onScanComplete;

  // Each finished sync refreshes the page underneath, so new findings just appear.
  useEffect(() => {
    if (!portal) return;
    const check = async () => {
      try {
        const status = await getSyncStatus();
        setSync(status);
        if (status.last_synced_at !== lastSynced.current) {
          if (lastSynced.current !== null) refreshPage.current?.();
          lastSynced.current = status.last_synced_at;
        }
      } catch {
        // The layout already shows when the backend is down.
      }
    };
    check();
    const timer = setInterval(check, 4000);
    return () => clearInterval(timer);
  }, [portal]);

  const handleSync = async () => {
    try {
      await startSync();
      setSync((current) => (current ? { ...current, state: 'syncing' } : current));
    } catch (err) {
      setScanOk(false);
      setScanMessage(err instanceof Error ? err.message : 'Could not start a sync');
      setTimeout(() => setScanMessage(null), 5000);
    }
  };

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

  const syncing = sync?.state === 'syncing';

  return (
    <header className="h-14 border-b border-border bg-card px-6 flex items-center justify-between sticky top-0 z-40">
      {/* Breadcrumbs & Title */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-1.5 text-xs text-zinc-500">
          <span>docguard</span>
          <span>/</span>
        </div>
        <div>
          <h1 className="text-xs font-semibold text-ink tracking-tight uppercase">
            {title}
          </h1>
          {subtitle && (
            <p className="text-[11px] text-zinc-600 hidden md:block">
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
            className={`text-[11px] px-2.5 py-1 rounded-xl border flex items-center space-x-1.5 ${
              scanOk
                ? 'text-emerald-700 bg-emerald-950/20 border-emerald-500/30'
                : 'text-red-700 bg-red-950/20 border-red-500/30'
            }`}
          >
            {scanOk && <Check className="w-3 h-3" />}
            <span>{scanMessage}</span>
          </span>
        )}

        {portal ? (
          <>
            <span role="status" className="text-[11px] text-zinc-600 hidden sm:inline">
              {syncing
                ? 'Syncing with GitHub...'
                : sync?.last_synced_at
                ? `Synced ${timeAgo(sync.last_synced_at)}`
                : 'Waiting for first sync'}
            </span>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 transition-all text-white px-3.5 py-1.5 rounded-xl shadow-sm disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${syncing ? 'animate-spin' : ''}`} />
              <span>Sync now</span>
            </button>
          </>
        ) : (
          <button
            onClick={handleScan}
            disabled={scanning}
            className="flex items-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 active:scale-[0.98] transition-all text-white px-3.5 py-1.5 rounded-xl shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Scanning...' : 'Scan Last Commit'}</span>
          </button>
        )}
      </div>
    </header>
  );
}
