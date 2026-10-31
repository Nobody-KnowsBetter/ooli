'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { History, ShieldCheck } from 'lucide-react';
import { Header } from '@/components/Header';
import { GithubIcon } from '@/components/GithubIcon';
import { isPortal, useAuth } from '@/components/AuthContext';
import { getOverview, getRepositories, OverviewData, Repository } from '@/lib/api';

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const auth = useAuth();
  const portal = isPortal(auth);

  const loadAllData = async () => {
    try {
      setLoading(true);
      const [ovData, repoData] = await Promise.all([
        getOverview(),
        getRepositories(),
      ]);
      setOverview(ovData);
      setRepositories(repoData);
    } catch (err) {
      console.error('Failed to load overview data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const activeDrifts = overview?.total_active_drifts ?? 0;
  const isHealthy = activeDrifts === 0;
  const openIssues = overview?.recent_issues ?? [];
  const patchesApplied = overview?.resolved_drifts ?? 0;

  return (
    <>
      <Header
        title="Overview"
        subtitle="Documentation drift across your repositories"
        onScanComplete={loadAllData}
      />

      <main className="p-6 sm:p-8 space-y-8 flex-1 overflow-y-auto max-w-5xl w-full mx-auto">
        {/* 1. Hero Selected Repository Card (Vercel / Linear Style) */}
        <section className="bg-card border border-border rounded-xl p-6 sm:p-7 space-y-6 hover:border-zinc-400 transition">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
            <div className="flex items-center space-x-3 min-w-0">
              <div className="h-9 w-9 rounded-2xl bg-paper border border-border flex items-center justify-center text-ink shrink-0">
                <GithubIcon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-bold text-ink tracking-tight truncate">
                  {auth?.user ? `Welcome, ${auth.user.name}` : 'Your repositories'}
                </h2>
                <p className="text-xs text-zinc-600">
                  {portal ? 'Open pull requests are checked automatically.' : 'Scan a repository to check it.'}
                </p>
              </div>
            </div>

            <span
              className={`text-xs border px-3 py-1.5 rounded-xl flex items-center space-x-2 font-medium w-fit shrink-0 ${
                isHealthy
                  ? 'text-emerald-700 bg-emerald-500/10 border-emerald-500/20'
                  : 'text-red-700 bg-red-500/10 border-red-500/20'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${isHealthy ? 'bg-emerald-400' : 'bg-red-400'}`}></span>
              <span>{isHealthy ? 'No open drift' : `${activeDrifts} open ${activeDrifts === 1 ? 'issue' : 'issues'}`}</span>
            </span>
          </div>

          <dl className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { label: 'Repositories', value: overview?.repository_count ?? 0 },
              { label: 'Pull requests checked', value: overview?.prs_checked ?? 0 },
              { label: 'Open issues', value: activeDrifts },
              { label: 'Resolved', value: patchesApplied },
            ].map((stat) => (
              <div key={stat.label} className="space-y-1">
                <dt className="text-[11px] uppercase tracking-wider text-zinc-500">{stat.label}</dt>
                <dd className="text-3xl font-bold text-ink tracking-tight">{loading ? '...' : stat.value}</dd>
              </div>
            ))}
          </dl>

        </section>

        {/* 2. Side-by-Side Detail Cards: Health Scope & Applied Patches */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Card A: Current Repository Documentation Health */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4 hover:border-zinc-400 transition">
            <div className="flex items-center space-x-3 border-b border-border pb-3.5">
              <div className="h-8 w-8 rounded-2xl bg-emerald-500/10 text-emerald-700 border border-emerald-500/20 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-ink uppercase tracking-wider">
                  Open Drift
                </h3>
                <p className="text-xs text-zinc-600">
                  Sentences that need attention, across all repositories
                </p>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              {openIssues.length === 0 ? (
                <p className="bg-paper p-3 rounded-2xl border border-border text-zinc-600">
                  No open issues. Scan a commit or pull request to check it.
                </p>
              ) : (
                openIssues.map((issue) => (
                  <Link
                    key={issue.id}
                    href={`/dashboard/issues/${issue.id}`}
                    className="bg-paper p-3 rounded-2xl border border-border flex items-center justify-between gap-3 hover:border-zinc-400 transition"
                  >
                    <span className="text-zinc-700 truncate">
                      {issue.repo_id ? `${issue.repo_id} · ` : ''}
                      {issue.doc_file}:{issue.doc_start_line}
                    </span>
                    <span className="text-red-700 shrink-0">{issue.changed_symbol}</span>
                  </Link>
                ))
              )}
            </div>
          </div>

          {/* Card B: Recent checks */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4 hover:border-zinc-400 transition">
            <div className="flex items-center space-x-3 border-b border-border pb-3.5">
              <div className="h-8 w-8 rounded-2xl bg-zinc-100 border border-border text-ink flex items-center justify-center">
                <History className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-ink uppercase tracking-wider">Recent checks</h3>
                <p className="text-xs text-zinc-600">The latest pull requests and commits DocGuard looked at</p>
              </div>
            </div>
            <div className="space-y-2 text-xs">
              {(overview?.recent_reports ?? []).length === 0 ? (
                <p className="bg-paper p-3 rounded-2xl border border-border text-zinc-600">
                  Nothing checked yet. Open pull requests appear here after a sync.
                </p>
              ) : (
                (overview?.recent_reports ?? []).map((report) => (
                  <div
                    key={report.id}
                    className="bg-paper p-3 rounded-2xl border border-border flex items-center justify-between gap-3"
                  >
                    <span className="text-zinc-700 truncate">
                      {report.repo_id}
                      {report.pr_number ? ` · PR #${report.pr_number}` : ''}
                    </span>
                    <span className={`shrink-0 ${report.total_drifts ? 'text-red-700' : 'text-emerald-700'}`}>
                      {report.total_drifts ? `${report.total_drifts} found` : 'Clean'}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        {/* 3. Connected Repositories Section */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-ink uppercase tracking-wider">
              Your Repositories ({repositories.length})
            </h3>
            <Link
              href="/dashboard/repositories"
              className="text-xs text-zinc-600 hover:text-ink transition flex items-center space-x-1"
            >
              <span>View all &rarr;</span>
            </Link>
          </div>

          <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
            {repositories.slice(0, 8).map((repo) => (
              <div key={repo.id} className="p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <a
                    href={`https://github.com/${repo.full_name}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-semibold text-ink hover:underline truncate block"
                  >
                    {repo.full_name}
                  </a>
                  <p className="text-xs text-zinc-600">
                    {repo.open_prs ?? 0} open {repo.open_prs === 1 ? 'pull request' : 'pull requests'}
                  </p>
                </div>
                {(repo.open_issues ?? 0) > 0 ? (
                  <span className="text-xs text-red-700 shrink-0">{repo.open_issues} open</span>
                ) : (
                  <span className="text-xs text-zinc-500 shrink-0">{repo.last_scanned_at ? 'No open issues' : 'Not checked yet'}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}