'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  FileCode,
  FileText,
  Wand2,
  Check,
  CheckCircle2,
  GitCommit,
  Copy,
} from 'lucide-react';
import { Header } from '@/components/Header';
import { isPortal, useAuth } from '@/components/AuthContext';
import { getIssueById, applyFixForIssue, githubFileLinks, Issue } from '@/lib/api';

export default function IssueDetailPage() {
  const params = useParams();
  const issueId = params.id as string;

  const [issue, setIssue] = useState<Issue | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [fixSuccess, setFixSuccess] = useState(false);
  const [copied, setCopied] = useState(false);
  const portal = isPortal(useAuth());

  const loadIssue = async () => {
    try {
      setLoading(true);
      const data = await getIssueById(issueId);
      setIssue(data);
      if (data.is_fixed === 1) {
        setFixSuccess(true);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (issueId) {
      loadIssue();
    }
  }, [issueId]);

  const handleApplyFix = async () => {
    if (!issue) return;
    try {
      setApplying(true);
      const res = await applyFixForIssue(issue.id);
      if (res.success) {
        setFixSuccess(true);
        await loadIssue();
      }
    } catch (err) {
      alert('Failed to apply fix: ' + err);
    } finally {
      setApplying(false);
    }
  };

  const copyPatch = () => {
    if (!issue?.diff_preview) return;
    navigator.clipboard.writeText(issue.diff_preview);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="p-8 text-center text-xs text-zinc-500">
        Loading discrepancy details...
      </div>
    );
  }

  if (!issue) {
    return (
      <div className="p-8 text-center space-y-3">
        <p className="text-xs text-red-700">Discrepancy record not found.</p>
        <Link href="/dashboard/issues" className="text-xs text-zinc-600 underline">
          &larr; Back to all issues
        </Link>
      </div>
    );
  }

  const isConfirmed = issue.verdict === 'CONFIRMED_DRIFT';

  const links = githubFileLinks(issue.repo_id, issue.doc_file, issue.doc_start_line, issue.head_sha, issue.default_branch);

  return (
    <>
      <Header
        title={`Issue: ${issue.changed_symbol}`}
        subtitle={`${issue.repo_id ?? ''}${issue.pr_number ? ` · PR #${issue.pr_number}` : ''}`}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-5xl w-full mx-auto">
        {/* Navigation & Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div className="space-y-1">
            <Link
              href="/dashboard/issues"
              className="text-xs text-zinc-600 hover:text-ink flex items-center space-x-1.5 transition mb-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Issues</span>
            </Link>
            <div className="flex items-center space-x-2.5">
              <span
                className={`px-2 py-0.5 rounded-xl text-[10px] font-medium ${
                  fixSuccess
                    ? 'bg-emerald-500/10 text-emerald-700 border border-emerald-500/20'
                    : isConfirmed
                    ? 'bg-red-500/10 text-red-700 border border-red-500/20'
                    : 'bg-zinc-100 text-zinc-700 border border-zinc-300'
                }`}
              >
                {fixSuccess
                  ? 'RESOLVED'
                  : isConfirmed
                  ? 'CONFIRMED DRIFT'
                  : 'POSSIBLE DRIFT'}
              </span>
              <h2 className="text-base font-bold text-ink">
                {issue.changed_symbol}
              </h2>
              <span className="text-xs text-zinc-500">
                Confidence: <b className="text-ink">{Math.round(issue.confidence * 100)}%</b>
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {portal ? (
              <>
                {links && (
                  <a
                    href={links.view}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-medium border border-border hover:border-zinc-400 text-zinc-700 px-3.5 py-2 rounded-xl transition"
                  >
                    View on GitHub
                  </a>
                )}
                {links && (
                  <a
                    href={links.edit}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition"
                  >
                    <Wand2 className="w-3.5 h-3.5" />
                    <span>Edit on GitHub</span>
                  </a>
                )}
              </>
            ) : fixSuccess ? (
              <span className="text-xs text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 px-3.5 py-1.5 rounded-xl flex items-center space-x-1.5">
                <Check className="w-3.5 h-3.5" />
                <span>Patch Applied</span>
              </span>
            ) : (
              <button
                onClick={handleApplyFix}
                disabled={applying || !issue.suggested_fix}
                className="flex items-center space-x-2 text-xs font-semibold bg-ink hover:bg-zinc-700 text-white px-4 py-2 rounded-xl transition shadow-sm disabled:opacity-50"
              >
                <Wand2 className="w-3.5 h-3.5" />
                <span>{applying ? 'Applying Patch...' : 'Apply Patch to File'}</span>
              </button>
            )}
          </div>
        </div>

        {/* Side-by-Side Comparison Panes */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: Code Reality */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-zinc-600">
              <span className="flex items-center space-x-1.5">
                <FileCode className="w-3.5 h-3.5 text-zinc-600" />
                <span className="text-ink font-medium">{issue.source_file}</span>
              </span>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                Code Truth
              </span>
            </div>

            <div className="bg-paper rounded-2xl p-3.5 text-xs border border-border min-h-[140px] flex flex-col justify-center">
              <pre className="text-zinc-700 leading-relaxed whitespace-pre-wrap">
                {issue.code_diff || `Symbol: ${issue.changed_symbol}`}
              </pre>
            </div>
          </div>

          {/* Right: Outdated Documentation */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-zinc-600">
              <span className="flex items-center space-x-1.5">
                <FileText className="w-3.5 h-3.5 text-zinc-600" />
                <span className="text-ink font-medium">
                  {issue.doc_file}:{issue.doc_start_line}
                </span>
              </span>
              <span className="text-[10px] uppercase tracking-wider text-red-700">
                Contradiction
              </span>
            </div>

            <div className="bg-paper rounded-2xl p-3.5 font-sans text-xs border border-border min-h-[140px] flex flex-col justify-center space-y-2">
              <blockquote className="border-l-2 border-red-500 pl-3 text-red-300 text-xs">
                &ldquo;{issue.outdated_excerpt}&rdquo;
              </blockquote>
              <p className="text-zinc-600 text-xs">{issue.explanation}</p>
            </div>
          </div>
        </div>

        {/* Suggested Fix Section */}
        {issue.suggested_fix && (
          <div className="bg-card border border-emerald-500/20 p-4 rounded-2xl space-y-2">
            <div className="flex items-center space-x-1.5 text-emerald-700 text-xs font-semibold uppercase tracking-wider">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Recommended Documentation Patch</span>
            </div>
            <div className="p-3 bg-paper rounded-xl border border-emerald-500/20 text-xs text-emerald-300">
              {issue.suggested_fix}
            </div>
          </div>
        )}

        {/* Evidence Chain */}
        {issue.evidence && issue.evidence.length > 0 && (
          <div className="bg-card border border-border p-4 rounded-2xl space-y-2">
            <h3 className="text-xs font-semibold text-ink uppercase tracking-wider">
              Verification Evidence
            </h3>
            <ul className="space-y-1.5 text-xs text-zinc-600 list-disc list-inside">
              {issue.evidence.map((ev, i) => (
                <li key={i}>{ev}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Unified Patch Diff */}
        {issue.diff_preview && (
          <div className="bg-card border border-border p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-ink uppercase tracking-wider">
                Unified Patch Diff
              </h3>
              <button
                onClick={copyPatch}
                className="text-[11px] text-zinc-600 hover:text-ink flex items-center space-x-1"
              >
                <Copy className="w-3 h-3" />
                <span>{copied ? 'Copied' : 'Copy Diff'}</span>
              </button>
            </div>
            <div className="bg-paper rounded-xl p-3 text-xs overflow-x-auto border border-border space-y-0.5">
              {issue.diff_preview.split('\n').map((line, idx) => {
                if (line.startsWith('+')) {
                  return <div key={idx} className="text-emerald-700 bg-emerald-950/20 px-1 py-0.5 rounded-xl">{line}</div>;
                } else if (line.startsWith('-')) {
                  return <div key={idx} className="text-red-700 bg-red-950/20 px-1 py-0.5 rounded-xl">{line}</div>;
                }
                return <div key={idx} className="text-zinc-500 px-1 py-0.5">{line}</div>;
              })}
            </div>
          </div>
        )}
      </main>
    </>
  );
}