'use client';

import { useEffect, useState } from 'react';
import {
  Wand2,
  CheckCircle2,
  Check,
  Copy,
  ExternalLink,
  GitCommit,
  Pencil,
} from 'lucide-react';
import { isPortal, useAuth } from '@/components/AuthContext';
import { Header } from '@/components/Header';
import { getAutoFixProposals, applyFixForIssue, AutoFixProposal, githubFileLinks } from '@/lib/api';

export default function AutoFixPage() {
  const [proposals, setProposals] = useState<AutoFixProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const portal = isPortal(useAuth());

  const copyFix = async (proposal: AutoFixProposal) => {
    await navigator.clipboard.writeText(proposal.suggested_fix);
    setCopiedId(proposal.issue_id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const loadProposals = async () => {
    try {
      setLoading(true);
      const data = await getAutoFixProposals();
      setProposals(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProposals();
  }, []);

  const handleApply = async (proposal: AutoFixProposal) => {
    try {
      setApplyingId(proposal.issue_id);
      const res = await applyFixForIssue(proposal.issue_id);
      if (res.success) {
        setAppliedIds((prev) => new Set(prev).add(proposal.issue_id));
        setTimeout(() => loadProposals(), 1500);
      }
    } catch (err) {
      alert('Failed to apply fix: ' + err);
    } finally {
      setApplyingId(null);
    }
  };

  return (
    <>
      <Header
        title="Fixes"
        subtitle="Suggested corrections for the sentences that drifted"
        onScanComplete={loadProposals}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-6xl w-full mx-auto">
        {/* Banner */}
        <div className="bg-card border border-border p-4 sm:p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-xs font-semibold text-ink uppercase tracking-wider flex items-center space-x-2">
              <GitCommit className="w-4 h-4 text-zinc-600" />
              <span>Review every fix</span>
            </h2>
            <p className="text-xs text-zinc-600">
              {portal
                ? 'Copy the corrected sentence and paste it in GitHub\'s editor. DocGuard never changes your repository.'
                : 'Each fix replaces one sentence in the local copy of the docs. Nothing is committed for you.'}
            </p>
          </div>
          <div className="text-xs text-zinc-700 bg-paper px-3 py-1.5 rounded-xl border border-border w-fit shrink-0">
            <span>{proposals.length} {proposals.length === 1 ? 'fix' : 'fixes'} waiting</span>
          </div>
        </div>

        {/* Proposals List */}
        {loading ? (
          <div className="bg-card border border-border p-12 rounded-2xl text-center text-xs text-zinc-500">
            Calculating unified patch diffs...
          </div>
        ) : proposals.length === 0 ? (
          <div className="bg-card border border-border p-12 rounded-2xl text-center space-y-3">
            <div className="h-10 w-10 rounded-full bg-emerald-500/10 text-emerald-700 mx-auto flex items-center justify-center border border-emerald-500/20">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-ink">Nothing to fix</h3>
            <p className="text-xs text-zinc-600 max-w-sm mx-auto">
              No open issue has a fix waiting. New ones appear here after the next sync.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {proposals.map((p) => {
              const isApplied = appliedIds.has(p.issue_id);
              const isApplying = applyingId === p.issue_id;
              const links = githubFileLinks(p.repo_id, p.doc_file, p.doc_start_line, p.head_sha, p.default_branch);

              return (
                <div
                  key={p.issue_id}
                  className="bg-card border border-border hover:border-zinc-400 p-5 rounded-2xl space-y-4 transition"
                >
                  {/* Proposal Top Bar */}
                  <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3 border-b border-border pb-3">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2.5">
                        <span className=" text-xs font-bold text-ink">
                          {p.changed_symbol}
                        </span>
                        <span className="text-xs text-zinc-600">
                          in {p.doc_file}:{p.doc_start_line}
                        </span>
                      </div>
                      <p className="text-[11px] font-medium text-zinc-700">
                        {p.repo_id}
                        {p.pr_number ? ` · PR #${p.pr_number}` : ''}
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 shrink-0">
                      {portal ? (
                        <>
                          {p.suggested_fix && (
                            <button
                              type="button"
                              onClick={() => copyFix(p)}
                              className="flex items-center space-x-1.5 text-xs font-medium border border-border hover:border-zinc-400 text-zinc-700 px-3 py-2 rounded-xl transition"
                            >
                              <Copy className="w-3.5 h-3.5" />
                              <span>{copiedId === p.issue_id ? 'Copied' : 'Copy fix'}</span>
                            </button>
                          )}
                          <a
                            href={links?.view}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center space-x-1.5 text-xs font-medium border border-border hover:border-zinc-400 text-zinc-700 px-3 py-2 rounded-xl transition"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            <span>View</span>
                          </a>
                          <a
                            href={links?.edit}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center space-x-1.5 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                            <span>Edit on GitHub</span>
                          </a>
                        </>
                      ) : isApplied ? (
                        <span className="text-xs text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 px-3.5 py-1.5 rounded-xl flex items-center space-x-1.5 font-medium">
                          <Check className="w-3.5 h-3.5" />
                          <span>Patch Applied</span>
                        </span>
                      ) : (
                        <button
                          onClick={() => handleApply(p)}
                          disabled={isApplying}
                          className="flex items-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition disabled:opacity-50 shadow-sm"
                        >
                          <Wand2 className="w-3.5 h-3.5" />
                          <span>{isApplying ? 'Applying...' : 'Apply Patch to File'}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Unified Diff */}
                  <div className="space-y-2">
                    <span className="text-[11px] uppercase tracking-wider text-zinc-600">
                      The change
                    </span>
                    <div className="bg-paper rounded-xl p-3.5 text-xs overflow-x-auto border border-border space-y-0.5">
                      {portal || !p.diff ? (
                        <>
                          <div className="text-red-700 bg-red-500/10 px-1 py-0.5 rounded-xl">- {p.outdated_excerpt}</div>
                          {p.suggested_fix ? (
                            <div className="text-emerald-700 bg-emerald-500/10 px-1 py-0.5 rounded-xl">+ {p.suggested_fix}</div>
                          ) : (
                            <div className="text-zinc-600 px-1 py-0.5">This one needs rewriting by hand.</div>
                          )}
                        </>
                      ) : (
                        p.diff.split('\n').map((line, idx) => {
                          if (line.startsWith('+')) {
                            return (
                              <div key={idx} className="text-emerald-700 bg-emerald-500/10 px-1 py-0.5 rounded-xl">
                                {line}
                              </div>
                            );
                          } else if (line.startsWith('-')) {
                            return (
                              <div key={idx} className="text-red-700 bg-red-500/10 px-1 py-0.5 rounded-xl">
                                {line}
                              </div>
                            );
                          }
                          return (
                            <div key={idx} className="text-zinc-500 px-1 py-0.5">
                              {line}
                            </div>
                          );
                        })
                      )}
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