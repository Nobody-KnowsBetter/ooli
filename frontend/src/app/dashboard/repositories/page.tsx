'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ExternalLink, GitBranch, GitPullRequest, Lock, Plus, RefreshCw, Search } from 'lucide-react';
import { isPortal, useAuth } from '@/components/AuthContext';
import { Header } from '@/components/Header';
import { GithubIcon } from '@/components/GithubIcon';
import {
  addRepository,
  describeScan,
  getPullRequests,
  getRepositories,
  PullRequest,
  Repository,
  setSelectedRepo,
  triggerLiveScan,
} from '@/lib/api';

export default function RepositoriesPage() {
  const auth = useAuth();
  const portal = isPortal(auth);
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [scanningRepo, setScanningRepo] = useState<string | null>(null);
  const [newRepo, setNewRepo] = useState('');
  const [adding, setAdding] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pulls, setPulls] = useState<Record<string, PullRequest[]>>({});
  const [prNumbers, setPrNumbers] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const loadRepos = async () => {
    try {
      setRepos(await getRepositories());
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not load your repositories');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRepos();
  }, []);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return repos.filter((repo) => repo.full_name.toLowerCase().includes(query));
  }, [repos, search]);

  const toggle = (repo: Repository) => {
    setExpanded(expanded === repo.id ? null : repo.id);
    if (portal && !pulls[repo.id]) {
      getPullRequests(repo.full_name)
        .then((list) => setPulls((current) => ({ ...current, [repo.id]: list })))
        .catch(() => setPulls((current) => ({ ...current, [repo.id]: [] })));
    }
  };

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
      setMessage({ ok: true, text: `Added ${repo.full_name}.` });
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
        title="Repositories"
        subtitle={portal ? 'Your GitHub repositories, kept in sync automatically' : 'Repositories to check for documentation drift'}
        onScanComplete={loadRepos}
      />

      <main className="p-6 space-y-5 flex-1 overflow-y-auto max-w-5xl w-full mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${repos.length} repositories`}
              aria-label="Search repositories"
              className="w-full bg-card border border-border rounded-xl pl-9 pr-3.5 py-2.5 text-xs text-ink focus:outline-none focus:border-zinc-500"
            />
          </div>
          {portal && auth?.private_repos_allowed && !auth.can_read_private && (
            <a href="/api/auth/login?private=true" className="text-xs text-zinc-600 hover:text-ink underline shrink-0">
              Include private repositories
            </a>
          )}
        </div>

        {!portal && (
          <form onSubmit={handleAdd} className="bg-card border border-border p-4 rounded-2xl flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={newRepo}
              onChange={(e) => setNewRepo(e.target.value)}
              placeholder="owner/name or https://github.com/owner/name"
              aria-label="GitHub repository"
              className="flex-1 min-w-0 bg-paper border border-border rounded-xl px-3.5 py-2 text-xs text-ink focus:outline-none focus:border-zinc-500"
            />
            <button
              type="submit"
              disabled={adding || !newRepo.trim()}
              className="flex items-center justify-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{adding ? 'Cloning...' : 'Add Repository'}</span>
            </button>
          </form>
        )}

        {message && (
          <p role="status" className={`text-xs ${message.ok ? 'text-emerald-700' : 'text-red-700'}`}>
            {message.text}
          </p>
        )}

        {loadError && (
          <p role="alert" className="text-xs text-red-700">
            {loadError}
          </p>
        )}

        {loading ? (
          <div className="bg-card border border-border p-12 rounded-2xl text-center text-xs text-zinc-500">
            Loading your repositories from GitHub...
          </div>
        ) : visible.length === 0 ? (
          <div className="bg-card border border-border p-12 rounded-2xl text-center text-xs text-zinc-600">
            {search ? 'No repositories match that search.' : 'No repositories found on this GitHub account.'}
          </div>
        ) : (
          <ul className="bg-card border border-border rounded-2xl divide-y divide-border overflow-hidden">
            {visible.map((repo) => {
              const issues = repo.open_issues ?? 0;
              const isOpen = expanded === repo.id;
              return (
                <li key={repo.id}>
                  <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <button type="button" onClick={() => toggle(repo)} aria-expanded={isOpen} className="text-left min-w-0 flex-1">
                      <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                        {repo.is_private ? <Lock className="w-3 h-3 text-zinc-500 shrink-0" aria-label="Private" /> : null}
                        <span className="truncate">{repo.full_name}</span>
                      </span>
                      {repo.description && <span className="block text-xs text-zinc-600 truncate mt-0.5">{repo.description}</span>}
                      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-zinc-600 mt-1">
                        {repo.language && <span>{repo.language}</span>}
                        <span className="flex items-center gap-1">
                          <GitBranch className="w-3 h-3" />
                          {repo.default_branch}
                        </span>
                        <span className="flex items-center gap-1">
                          <GitPullRequest className="w-3 h-3" />
                          {repo.open_prs ?? 0} open
                        </span>
                        <span>
                          {repo.last_scanned_at
                            ? `Checked ${new Date(repo.last_scanned_at).toLocaleString()}`
                            : 'Not checked yet'}
                        </span>
                      </span>
                    </button>

                    <div className="flex items-center gap-3 shrink-0">
                      {issues > 0 ? (
                        <Link
                          href="/dashboard/issues"
                          className="text-xs font-medium text-red-700 bg-red-500/10 border border-red-500/20 px-2.5 py-1 rounded-xl"
                        >
                          {issues} open {issues === 1 ? 'issue' : 'issues'}
                        </Link>
                      ) : repo.last_scanned_at ? (
                        <span className="text-xs text-emerald-700">No open issues</span>
                      ) : null}
                      <a
                        href={`https://github.com/${repo.full_name}`}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open ${repo.full_name} on GitHub`}
                        className="text-zinc-500 hover:text-ink transition"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="px-4 pb-4 flex flex-col sm:flex-row sm:items-center gap-3">
                      {pulls[repo.id]?.length ? (
                        <select
                          value={prNumbers[repo.id] ?? ''}
                          onChange={(e) => setPrNumbers({ ...prNumbers, [repo.id]: e.target.value })}
                          aria-label={`Pull request for ${repo.full_name}`}
                          className="flex-1 min-w-0 bg-paper border border-border rounded-xl px-2.5 py-2 text-xs text-ink focus:outline-none focus:border-zinc-500"
                        >
                          <option value="">Last commit</option>
                          {pulls[repo.id].map((pull) => (
                            <option key={pull.number} value={pull.number}>
                              #{pull.number} {pull.title} ({pull.state})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          min="1"
                          value={prNumbers[repo.id] ?? ''}
                          onChange={(e) => setPrNumbers({ ...prNumbers, [repo.id]: e.target.value })}
                          placeholder="PR number (optional)"
                          aria-label={`Pull request number for ${repo.full_name}`}
                          className="flex-1 min-w-0 bg-paper border border-border rounded-xl px-2.5 py-2 text-xs text-ink focus:outline-none focus:border-zinc-500"
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => handleScan(repo.id)}
                        disabled={scanningRepo !== null}
                        className="flex items-center justify-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition disabled:opacity-50 shrink-0"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${scanningRepo === repo.id ? 'animate-spin' : ''}`} />
                        <span>{scanningRepo === repo.id ? 'Scanning...' : 'Scan now'}</span>
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </>
  );
}
