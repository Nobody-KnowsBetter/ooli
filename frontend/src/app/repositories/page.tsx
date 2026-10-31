'use client';

import { useEffect, useState } from 'react';
import { GitBranch, RefreshCw, ExternalLink, ShieldCheck, FileText, Check } from 'lucide-react';
import { Header } from '@/components/Header';
import { getRepositories, Repository, triggerLiveScan } from '@/lib/api';
import { GithubIcon } from '@/components/GithubIcon';

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanningRepo, setScanningRepo] = useState<string | null>(null);

  const loadRepos = async () => {
    try {
      setLoading(true);
      const data = await getRepositories();
      setRepos(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const handleScan = async (repoName: string) => {
    setScanningRepo(repoName);
    try {
      await triggerLiveScan('HEAD~1', 'HEAD');
      await loadRepos();
    } catch (err) {
      alert('Scan error: ' + err);
    } finally {
      setScanningRepo(null);
    }
  };

  return (
    <>
      <Header
        title="Monitored Repositories"
        subtitle="Connected codebases evaluated for documentation drift"
        onScanComplete={loadRepos}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-6xl w-full mx-auto">
        {/* Banner summary */}
        <div className="bg-card border border-border p-4 sm:p-5 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-xs font-semibold text-white uppercase tracking-wider font-mono flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-zinc-400" />
              <span>Repository Coverage &amp; Integration</span>
            </h2>
            <p className="text-xs text-zinc-400">
              Repositories monitored via GitHub Actions CI and REST webhook listeners. Each commit is audited against markdown prose.
            </p>
          </div>
          <div className="text-xs font-mono text-zinc-300 bg-black px-3 py-1.5 rounded border border-border w-fit shrink-0">
            <span>{repos.length} Connected {repos.length === 1 ? 'Repository' : 'Repositories'}</span>
          </div>
        </div>

        {/* Repositories List */}
        {loading ? (
          <div className="bg-card border border-border p-12 rounded-lg text-center font-mono text-xs text-zinc-500">
            Querying repository status...
          </div>
        ) : (
          <div className="space-y-4">
            {repos.map((repo) => {
              const score = Math.round(repo.health_score);
              const isHealthy = score >= 90;

              return (
                <div
                  key={repo.id}
                  className="bg-card border border-border rounded-lg p-5 space-y-4 hover:border-zinc-700 transition"
                >
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center space-x-3">
                        <div className="h-9 w-9 rounded-md bg-black border border-border flex items-center justify-center text-white">
                          <GithubIcon className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-white text-sm flex items-center space-x-2">
                            <span className="font-mono">{repo.full_name}</span>
                            <a
                              href={`https://github.com/${repo.full_name}`}
                              target="_blank"
                              rel="noreferrer"
                              className="text-zinc-500 hover:text-white transition"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </h3>
                          <div className="flex items-center space-x-2.5 text-[11px] text-zinc-400 font-mono mt-0.5">
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

                      <p className="text-xs text-zinc-400">
                        Last audited:{' '}
                        <span className="font-mono text-zinc-300">
                          {repo.last_scanned_at
                            ? new Date(repo.last_scanned_at).toLocaleString()
                            : 'Just now'}
                        </span>
                      </p>
                    </div>

                    {/* Right health & scan trigger */}
                    <div className="flex items-center space-x-5 border-t md:border-t-0 border-border pt-3 md:pt-0">
                      <div className="text-right">
                        <span className="text-[10px] uppercase font-mono tracking-wider text-zinc-400 block">
                          Sync Health
                        </span>
                        <span
                          className={`text-xl font-bold font-mono ${
                            isHealthy ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {score}%
                        </span>
                      </div>

                      <button
                        onClick={() => handleScan(repo.full_name)}
                        disabled={scanningRepo === repo.full_name}
                        className="flex items-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 text-black px-4 py-2 rounded transition shadow-sm disabled:opacity-50 font-mono"
                      >
                        <RefreshCw
                          className={`w-3.5 h-3.5 ${
                            scanningRepo === repo.full_name ? 'animate-spin' : ''
                          }`}
                        />
                        <span>{scanningRepo === repo.full_name ? 'Auditing...' : 'Run Audit'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Monitored targets details */}
                  <div className="pt-3 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                    <div className="bg-black p-3 rounded border border-border flex items-center justify-between">
                      <span className="text-zinc-400">Tracked Documentation</span>
                      <span className="text-white">2 Targets (README.md, docs/configuration.md)</span>
                    </div>
                    <div className="bg-black p-3 rounded border border-border flex items-center justify-between">
                      <span className="text-zinc-400">Analysis Coverage</span>
                      <span className="text-emerald-400 flex items-center space-x-1">
                        <Check className="w-3 h-3" />
                        <span>AST Constants, Functions, API</span>
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}