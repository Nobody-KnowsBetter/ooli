'use client';

import { useEffect, useState } from 'react';
import { GitBranch, RefreshCw, ExternalLink, ShieldCheck, Plus } from 'lucide-react';
import { Header } from '@/components/Header';
import { addRepository, describeScan, getRepositories, Repository, setSelectedRepo, triggerLiveScan } from '@/lib/api';
import { GithubIcon } from '@/components/GithubIcon';

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanningRepo, setScanningRepo] = useState<string | null>(null);
  const [newRepo, setNewRepo] = useState('');
  const [adding, setAdding] = useState(false);
  const [prNumbers, setPrNumbers] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

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

  const handleScan = async (repoId: string) => {
    const prNumber = Number(prNumbers[repoId]) || undefined;
    setScanningRepo(repoId);
    setMessage(null);
    try {
      setSelectedRepo(repoId);
      const result = await triggerLiveScan({ repoId, prNumber });
      const target = prNumber ? `PR #${prNumber}` : 'the last commit';
      setMessage({ ok: result.total_drifts === 0, text: describeScan(result, `${target} of ${repoId}`) });
      await loadRepos();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : 'Scan failed' });
    } finally {
      setScanningRepo(null);
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdding(true);
    setMessage(null);
    try {
      const repo = await addRepository(newRepo);
      setSelectedRepo(repo.id);
      setNewRepo('');
      setMessage({ ok: true, text: `Added ${repo.full_name}. Enter a PR number to scan a pull request.` });
      await loadRepos();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : 'Could not add repository' });
    } finally {
      setAdding(false);
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
              Add a public GitHub repository, then scan its last commit or any pull request. Scans compare the code change with the docs at that commit.
            </p>
          </div>
          <div className="text-xs font-mono text-zinc-300 bg-black px-3 py-1.5 rounded border border-border w-fit shrink-0">
            <span>{repos.length} {repos.length === 1 ? 'Repository' : 'Repositories'}</span>
          </div>
        </div>

        {/* Add repository */}
        <form onSubmit={handleAdd} className="bg-card border border-border p-4 rounded-lg flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={newRepo}
            onChange={(e) => setNewRepo(e.target.value)}
            placeholder="owner/name or https://github.com/owner/name"
            aria-label="GitHub repository"
            className="flex-1 min-w-0 bg-black border border-border rounded px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-zinc-500"
          />
          <button
            type="submit"
            disabled={adding || !newRepo.trim()}
            className="flex items-center justify-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 text-black px-4 py-2 rounded transition disabled:opacity-50 font-mono"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{adding ? 'Cloning...' : 'Add Repository'}</span>
          </button>
        </form>

        {message && (
          <p role="status" className={`text-xs font-mono ${message.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {message.text}
          </p>
        )}

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
                          </div>
                        </div>
                      </div>

                      <p className="text-xs text-zinc-400">
                        Last audited:{' '}
                        <span className="font-mono text-zinc-300">
                          {repo.last_scanned_at
                            ? new Date(repo.last_scanned_at).toLocaleString()
                            : 'Not scanned yet'}
                        </span>
                      </p>
                    </div>

                    {/* Right health & scan trigger */}
                    <div className="flex items-center space-x-5 border-t md:border-t-0 border-border pt-3 md:pt-0">
                      <div className="text-right">
                        <span className="text-[10px] uppercase font-mono tracking-wider text-zinc-400 block">
                          Last Scan
                        </span>
                        <span
                          className={`text-xl font-bold font-mono ${
                            isHealthy ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {score}%
                        </span>
                      </div>

                      <input
                        type="number"
                        min="1"
                        value={prNumbers[repo.id] ?? ''}
                        onChange={(e) => setPrNumbers({ ...prNumbers, [repo.id]: e.target.value })}
                        placeholder="PR #"
                        aria-label={`Pull request number for ${repo.full_name}`}
                        className="w-20 bg-black border border-border rounded px-2.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-zinc-500"
                      />
                      <button
                        onClick={() => handleScan(repo.id)}
                        disabled={scanningRepo !== null}
                        className="flex items-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 text-black px-4 py-2 rounded transition shadow-sm disabled:opacity-50 font-mono"
                      >
                        <RefreshCw
                          className={`w-3.5 h-3.5 ${
                            scanningRepo === repo.id ? 'animate-spin' : ''
                          }`}
                        />
                        <span>
                          {scanningRepo === repo.id ? 'Scanning...' : prNumbers[repo.id] ? 'Scan PR' : 'Scan Last Commit'}
                        </span>
                      </button>
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