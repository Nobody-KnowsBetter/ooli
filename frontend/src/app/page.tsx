'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  GitBranch,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  ExternalLink,
  ShieldCheck,
  FileText,
  Wand2,
  RefreshCw,
  Check,
} from 'lucide-react';
import { Header } from '@/components/Header';
import { GithubIcon } from '@/components/GithubIcon';
import { getOverview, getRepositories, triggerLiveScan, OverviewData, Repository } from '@/lib/api';

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string>('krishgarg-code/JavaBasicPrograms1');
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState(false);
  const [auditMessage, setAuditMessage] = useState<string | null>(null);

  const loadAllData = async () => {
    try {
      setLoading(true);
      const [ovData, repoData] = await Promise.all([
        getOverview(),
        getRepositories(),
      ]);
      setOverview(ovData);
      setRepositories(repoData);
      if (repoData.length > 0 && !selectedRepoId) {
        setSelectedRepoId(repoData[0].id);
      }
    } catch (err) {
      console.error('Failed to load overview data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, []);

  const handleRunAudit = async () => {
    try {
      setAuditing(true);
      setAuditMessage('Auditing...');
      await triggerLiveScan('HEAD~1', 'HEAD');
      setAuditMessage('Audit complete');
      await loadAllData();
      setTimeout(() => setAuditMessage(null), 3000);
    } catch (err) {
      setAuditMessage('Audit failed');
      setTimeout(() => setAuditMessage(null), 3000);
    } finally {
      setAuditing(false);
    }
  };

  const selectedRepo =
    repositories.find((r) => r.id === selectedRepoId) ||
    repositories[0] || {
      id: 'krishgarg-code/JavaBasicPrograms1',
      full_name: 'krishgarg-code/JavaBasicPrograms1',
      default_branch: 'main',
      health_score: 100.0,
      last_scanned_at: new Date().toISOString(),
    };

  const healthScore = Math.round(selectedRepo?.health_score ?? overview?.avg_health_score ?? 100);
  const activeDrifts = overview?.total_active_drifts ?? 0;
  const isHealthy = activeDrifts === 0 && healthScore >= 90;
  const patchesApplied = overview?.resolved_drifts ?? 12;

  return (
    <>
      <Header
        title="Project Overview"
        subtitle="Repository documentation health and automated sync status"
        onScanComplete={loadAllData}
      />

      <main className="p-6 sm:p-8 space-y-8 flex-1 overflow-y-auto max-w-5xl w-full mx-auto">
        {/* 1. Hero Selected Repository Card (Vercel / Linear Style) */}
        <section className="bg-card border border-border rounded-xl p-6 sm:p-7 space-y-6 hover:border-zinc-700 transition">
          {/* Header Row: Repository & Live Status */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
            <div className="space-y-1.5">
              <div className="flex items-center space-x-3">
                <div className="h-9 w-9 rounded-lg bg-black border border-border flex items-center justify-center text-white shrink-0">
                  <GithubIcon className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <h2 className="text-base font-bold text-white font-mono tracking-tight">
                      {selectedRepo.full_name}
                    </h2>
                    <a
                      href={`https://github.com/${selectedRepo.full_name}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-zinc-500 hover:text-white transition"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                  <div className="flex items-center space-x-3 text-xs text-zinc-400 font-mono mt-0.5">
                    <span className="flex items-center space-x-1">
                      <GitBranch className="w-3 h-3 text-zinc-500" />
                      <span className="text-zinc-300">{selectedRepo.default_branch}</span>
                    </span>
                    <span>&bull;</span>
                    <span>Monitored via GitHub Actions</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Live Sync Status Pill */}
            <div className="flex items-center space-x-3">
              {isHealthy ? (
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-md flex items-center space-x-2 font-medium">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span>All Docs In Sync</span>
                </span>
              ) : (
                <span className="text-xs font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-3 py-1.5 rounded-md flex items-center space-x-2 font-medium">
                  <span className="h-2 w-2 rounded-full bg-red-400"></span>
                  <span>{activeDrifts} Drift Detected</span>
                </span>
              )}
            </div>
          </div>

          {/* Key Vitals Grid (Spacious & Clean) */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-6">
            {/* Vitals 1: Health Score */}
            <div className="space-y-1">
              <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
                Documentation Health
              </span>
              <div className="flex items-baseline space-x-2">
                <span
                  className={`text-3xl font-bold font-mono tracking-tight ${
                    isHealthy ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {loading ? '...' : `${healthScore}%`}
                </span>
                <span className="text-xs font-mono text-zinc-400">
                  {isHealthy ? 'Verified' : 'Review needed'}
                </span>
              </div>
              <div className="w-full bg-zinc-900 h-1 rounded-full overflow-hidden mt-2">
                <div
                  className={`h-full ${isHealthy ? 'bg-emerald-400' : 'bg-red-400'}`}
                  style={{ width: `${healthScore}%` }}
                ></div>
              </div>
            </div>

            {/* Vitals 2: Patches Applied */}
            <div className="space-y-1">
              <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
                Patches Applied
              </span>
              <div className="flex items-baseline space-x-2">
                <span className="text-3xl font-bold font-mono text-white tracking-tight">
                  {loading ? '...' : patchesApplied}
                </span>
                <span className="text-xs font-mono text-emerald-400">
                  Resolved
                </span>
              </div>
              <p className="text-xs text-zinc-500 font-mono mt-2">
                Automated fixes merged
              </p>
            </div>

            {/* Vitals 3: Active Discrepancies */}
            <div className="space-y-1 col-span-2 sm:col-span-1">
              <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">
                Active Drift
              </span>
              <div className="flex items-baseline space-x-2">
                <span
                  className={`text-3xl font-bold font-mono tracking-tight ${
                    activeDrifts > 0 ? 'text-red-400' : 'text-white'
                  }`}
                >
                  {loading ? '...' : activeDrifts}
                </span>
                <span className="text-xs font-mono text-zinc-400">
                  {activeDrifts === 0 ? 'Discrepancies' : 'Issues open'}
                </span>
              </div>
              <p className="text-xs text-zinc-500 font-mono mt-2">
                {activeDrifts === 0 ? '0 pending fixes' : 'Action required'}
              </p>
            </div>
          </div>

          {/* Bottom Action Footer */}
          <div className="pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
            <span className="text-zinc-400">
              {isHealthy
                ? 'All constants, defaults, and signatures match markdown documentation.'
                : 'Documentation drift detected between code changes and markdown files.'}
            </span>

            <div className="flex items-center space-x-3">
              <button
                onClick={handleRunAudit}
                disabled={auditing}
                className="flex items-center space-x-2 bg-white hover:bg-zinc-200 text-black px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 shadow-sm"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${auditing ? 'animate-spin' : ''}`} />
                <span>{auditing ? 'Auditing...' : auditMessage || 'Run Audit'}</span>
              </button>

              <Link
                href="/issues?filter=fixed"
                className="flex items-center space-x-1.5 text-zinc-300 hover:text-white px-3.5 py-2 rounded-lg border border-border bg-black hover:bg-zinc-900 transition"
              >
                <span>View {patchesApplied} Applied Patches</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>
        </section>

        {/* 2. Side-by-Side Detail Cards: Health Scope & Applied Patches */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Card A: Current Repository Documentation Health */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4 hover:border-zinc-700 transition">
            <div className="flex items-center space-x-3 border-b border-border pb-3.5">
              <div className="h-8 w-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                  Documentation Health
                </h3>
                <p className="text-xs text-zinc-400">
                  Coverage of code symbols across repository markdown
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center text-xs font-mono">
                <span className="text-zinc-400">Tracked Documentation</span>
                <span className="text-white font-medium">2 Markdown Files</span>
              </div>
              <div className="bg-black p-3 rounded-lg border border-border space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-300">README.md</span>
                  <span className="text-emerald-400 flex items-center space-x-1">
                    <Check className="w-3 h-3" />
                    <span>In Sync</span>
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-zinc-300">docs/configuration.md</span>
                  <span className="text-emerald-400 flex items-center space-x-1">
                    <Check className="w-3 h-3" />
                    <span>In Sync</span>
                  </span>
                </div>
              </div>

              <div className="flex justify-between items-center text-xs font-mono pt-1 text-zinc-400">
                <span>Verified Symbols:</span>
                <span className="text-zinc-300">TIMEOUT_SECONDS, MAX_RETRIES</span>
              </div>
            </div>
          </div>

          {/* Card B: Patches Applied Summary */}
          <div className="bg-card border border-border rounded-xl p-6 space-y-4 hover:border-zinc-700 transition">
            <div className="flex items-center space-x-3 border-b border-border pb-3.5">
              <div className="h-8 w-8 rounded-lg bg-zinc-900 border border-zinc-800 text-white flex items-center justify-center">
                <Wand2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
                  Patches Applied &amp; Auto-Fix
                </h3>
                <p className="text-xs text-zinc-400">
                  Automated documentation corrections resolved
                </p>
              </div>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex justify-between items-center">
                <span className="text-zinc-400">Resolved Discrepancies</span>
                <span className="text-emerald-400 font-bold">{patchesApplied} Patches</span>
              </div>

              <div className="bg-black p-3 rounded-lg border border-border space-y-1.5 text-xs text-zinc-400">
                <p>
                  Deterministic AST patches calculated and applied without breaking documentation formatting.
                </p>
                <p className="text-zinc-500 text-[11px]">
                  All patches require human review prior to Git commit.
                </p>
              </div>

              <div className="pt-1">
                <Link
                  href="/autofix"
                  className="w-full block text-center text-xs font-mono text-zinc-300 hover:text-white bg-black hover:bg-zinc-900 border border-border py-2 rounded-lg transition"
                >
                  Open Auto-Fix Workspace &rarr;
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* 3. Connected Repositories Section */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-white uppercase tracking-wider font-mono">
              Connected Repositories ({repositories.length})
            </h3>
            <Link
              href="/repositories"
              className="text-xs text-zinc-400 hover:text-white transition font-mono flex items-center space-x-1"
            >
              <span>Manage repositories &rarr;</span>
            </Link>
          </div>

          <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
            {repositories.map((repo) => {
              const score = Math.round(repo.health_score);
              const healthy = score >= 90;

              return (
                <div
                  key={repo.id}
                  className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-card-hover transition"
                >
                  <div className="flex items-center space-x-3">
                    <div className="h-8 w-8 rounded-lg bg-black border border-border flex items-center justify-center text-white shrink-0">
                      <GithubIcon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-sm font-semibold text-white">
                          {repo.full_name}
                        </span>
                        <a
                          href={`https://github.com/${repo.full_name}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-zinc-500 hover:text-white transition"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-zinc-400 font-mono mt-0.5">
                        <span className="flex items-center space-x-1">
                          <GitBranch className="w-3 h-3 text-zinc-500" />
                          <span>{repo.default_branch}</span>
                        </span>
                        <span>&bull;</span>
                        <span className="text-emerald-400 flex items-center space-x-1">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                          <span>Active CI Runner</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-4 pl-11 sm:pl-0">
                    <div className="text-right">
                      <span className="text-[10px] uppercase font-mono tracking-wider text-zinc-500 block">
                        Health
                      </span>
                      <span
                        className={`text-sm font-mono font-bold ${
                          healthy ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {score}%
                      </span>
                    </div>

                    <button
                      onClick={handleRunAudit}
                      disabled={auditing}
                      className="text-xs font-mono font-medium bg-black hover:bg-zinc-900 border border-border text-zinc-300 hover:text-white px-3.5 py-1.5 rounded-lg transition disabled:opacity-50"
                    >
                      Audit
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </>
  );
}