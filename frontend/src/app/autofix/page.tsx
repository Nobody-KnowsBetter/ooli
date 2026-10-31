'use client';

import { useEffect, useState } from 'react';
import {
  Wand2,
  CheckCircle2,
  Check,
  GitCommit,
  FileCode,
  FileText,
  Copy,
} from 'lucide-react';
import { Header } from '@/components/Header';
import { getAutoFixProposals, applyFixForIssue, AutoFixProposal } from '@/lib/api';

export default function AutoFixPage() {
  const [proposals, setProposals] = useState<AutoFixProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());

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
        title="Patch Staging & Auto-Fix"
        subtitle="Review, approve, and apply deterministic documentation corrections"
        onScanComplete={loadProposals}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-6xl w-full mx-auto">
        {/* Banner */}
        <div className="bg-card border border-border p-4 sm:p-5 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-xs font-semibold text-white uppercase tracking-wider font-mono flex items-center space-x-2">
              <GitCommit className="w-4 h-4 text-zinc-400" />
              <span>Safe Patch Verification Workspace</span>
            </h2>
            <p className="text-xs text-zinc-400">
              DocGuard calculates exact unified diffs. No documentation updates are committed to Git without developer inspection and approval.
            </p>
          </div>
          <div className="text-xs font-mono text-zinc-300 bg-black px-3 py-1.5 rounded border border-border w-fit shrink-0">
            <span>{proposals.length} Pending {proposals.length === 1 ? 'Patch' : 'Patches'}</span>
          </div>
        </div>

        {/* Proposals List */}
        {loading ? (
          <div className="bg-card border border-border p-12 rounded-lg text-center font-mono text-xs text-zinc-500">
            Calculating unified patch diffs...
          </div>
        ) : proposals.length === 0 ? (
          <div className="bg-card border border-border p-12 rounded-lg text-center space-y-3">
            <div className="h-10 w-10 rounded-full bg-emerald-500/10 text-emerald-400 mx-auto flex items-center justify-center border border-emerald-500/20">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-white font-mono">No Pending Patches</h3>
            <p className="text-xs text-zinc-400 max-w-sm mx-auto">
              All identified drifts have been patched or the repository documentation is currently 100% in agreement with code.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {proposals.map((p) => {
              const isApplied = appliedIds.has(p.issue_id);
              const isApplying = applyingId === p.issue_id;

              return (
                <div
                  key={p.issue_id}
                  className="bg-card border border-border hover:border-zinc-700 p-5 rounded-lg space-y-4 transition"
                >
                  {/* Proposal Top Bar */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2.5">
                        <span className="font-mono text-xs font-bold text-white">
                          {p.changed_symbol}
                        </span>
                        <span className="text-xs font-mono text-zinc-400">
                          in {p.doc_file}:{p.doc_start_line}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-400 font-mono">
                        Contradiction: &ldquo;<span className="text-red-400">{p.outdated_excerpt}</span>&rdquo;
                      </p>
                    </div>

                    <div className="flex items-center space-x-3 shrink-0">
                      {isApplied ? (
                        <span className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3.5 py-1.5 rounded flex items-center space-x-1.5 font-medium font-mono">
                          <Check className="w-3.5 h-3.5" />
                          <span>Patch Applied</span>
                        </span>
                      ) : (
                        <button
                          onClick={() => handleApply(p)}
                          disabled={isApplying}
                          className="flex items-center space-x-2 text-xs font-semibold bg-white hover:bg-zinc-200 text-black px-4 py-2 rounded transition disabled:opacity-50 font-mono shadow-sm"
                        >
                          <Wand2 className="w-3.5 h-3.5" />
                          <span>{isApplying ? 'Applying...' : 'Apply Patch to File'}</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Unified Diff */}
                  <div className="space-y-2">
                    <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-400">
                      Unified Patch Preview
                    </span>
                    <div className="bg-black rounded p-3.5 font-mono text-xs overflow-x-auto border border-border space-y-0.5">
                      {p.diff ? (
                        p.diff.split('\n').map((line, idx) => {
                          if (line.startsWith('+')) {
                            return (
                              <div key={idx} className="text-emerald-400 bg-emerald-950/20 px-1 py-0.5 rounded">
                                {line}
                              </div>
                            );
                          } else if (line.startsWith('-')) {
                            return (
                              <div key={idx} className="text-red-400 bg-red-950/20 px-1 py-0.5 rounded">
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
                      ) : (
                        <div className="text-zinc-600">No diff preview generated</div>
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