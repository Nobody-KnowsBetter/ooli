'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  CheckCircle2,
  FileCode,
  FileText,
  ArrowRight,
  Filter,
  Check,
} from 'lucide-react';
import { Header } from '@/components/Header';
import { getIssues, Issue } from '@/lib/api';

export default function IssuesPage() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'open' | 'confirmed' | 'possible' | 'fixed' | 'all'>('open');

  const loadIssues = async () => {
    try {
      setLoading(true);
      let statusParam: string | undefined = undefined;
      let verdictParam: string | undefined = undefined;

      if (filter === 'open') statusParam = 'open';
      if (filter === 'fixed') statusParam = 'fixed';
      if (filter === 'confirmed') verdictParam = 'CONFIRMED_DRIFT';
      if (filter === 'possible') verdictParam = 'POSSIBLE_DRIFT';

      const data = await getIssues(statusParam, verdictParam);
      setIssues(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIssues();
  }, [filter]);

  return (
    <>
      <Header
        title="Discrepancies & Issues"
        subtitle="Active and resolved documentation drift identified by AST and semantic analysis"
        onScanComplete={loadIssues}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-7xl w-full mx-auto">
        {/* Filter Navigation Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'open', label: 'Active Drift' },
              { id: 'confirmed', label: 'Confirmed' },
              { id: 'possible', label: 'Possible' },
              { id: 'fixed', label: 'Resolved' },
              { id: 'all', label: 'All Recorded' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id as any)}
                className={`text-xs font-mono px-3 py-1.5 rounded transition ${
                  filter === tab.id
                    ? 'bg-white text-black font-semibold shadow-sm'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-900 border border-transparent'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="text-xs font-mono text-zinc-400 flex items-center space-x-1.5">
            <Filter className="w-3.5 h-3.5 text-zinc-400" />
            <span>
              {issues.length} {issues.length === 1 ? 'record' : 'records'} matching filter
            </span>
          </div>
        </div>

        {/* Content Area */}
        {loading ? (
          <div className="bg-card border border-border p-12 rounded-lg text-center font-mono text-xs text-zinc-500">
            Querying documentation drift index...
          </div>
        ) : issues.length === 0 ? (
          <div className="bg-card border border-border p-12 rounded-lg text-center space-y-3">
            <div className="h-10 w-10 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 mx-auto flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-white font-mono">
                {filter === 'open'
                  ? 'Zero Documentation Drift Detected'
                  : 'No Records Match Filter'}
              </h3>
              <p className="text-xs text-zinc-400 max-w-md mx-auto">
                {filter === 'open'
                  ? 'All monitored documentation targets in main match current code symbols, defaults, and API signatures.'
                  : 'Try selecting "Active Drift" or "Resolved" to inspect other records.'}
              </p>
            </div>
            {filter === 'open' && (
              <div className="pt-2">
                <button
                  onClick={() => setFilter('fixed')}
                  className="text-xs font-mono text-zinc-300 hover:text-white underline"
                >
                  View previously resolved and patched drifts &rarr;
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-card border border-border rounded-lg overflow-hidden divide-y divide-border">
            {issues.map((issue) => {
              const isConfirmed = issue.verdict === 'CONFIRMED_DRIFT';
              const isFixed = issue.is_fixed === 1;

              return (
                <Link
                  key={issue.id}
                  href={`/issues/${encodeURIComponent(issue.id)}`}
                  className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-card-hover transition group"
                >
                  <div className="space-y-1.5 min-w-0 pr-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                          isFixed
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : isConfirmed
                            ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                            : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                        }`}
                      >
                        {isFixed ? 'RESOLVED' : isConfirmed ? 'CONFIRMED DRIFT' : 'POSSIBLE DRIFT'}
                      </span>
                      <span className="font-mono text-xs font-bold text-white">
                        {issue.changed_symbol}
                      </span>
                      <span className="text-[11px] font-mono text-zinc-400">
                        {Math.round(issue.confidence * 100)}% Confidence
                      </span>
                    </div>

                    <p className="text-xs text-zinc-400">
                      {issue.explanation}
                    </p>

                    <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-zinc-400 pt-0.5">
                      <span className="flex items-center space-x-1.5 text-zinc-300">
                        <FileCode className="w-3.5 h-3.5 text-zinc-400" />
                        <span>{issue.source_file}</span>
                      </span>
                      <span>&bull;</span>
                      <span className="flex items-center space-x-1.5 text-zinc-300">
                        <FileText className="w-3.5 h-3.5 text-zinc-400" />
                        <span>
                          {issue.doc_file}:{issue.doc_start_line}
                        </span>
                      </span>
                      {issue.outdated_excerpt && (
                        <>
                          <span>&bull;</span>
                          <span className="text-red-400 truncate max-w-xs">
                            &ldquo;{issue.outdated_excerpt}&rdquo;
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center space-x-3 shrink-0">
                    <span className="text-xs font-mono text-zinc-400 group-hover:text-white transition flex items-center space-x-1">
                      <span>Inspect Diff</span>
                      <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition" />
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}