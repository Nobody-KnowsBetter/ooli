'use client';

import { useEffect, useState } from 'react';
import {
  History,
  GitCommit,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  GitPullRequest,
  Check,
  Calendar,
} from 'lucide-react';
import { Header } from '@/components/Header';
import { getReports, getReportById, ScanReport } from '@/lib/api';

export default function HistoryPage() {
  const [reports, setReports] = useState<ScanReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedReportId, setExpandedReportId] = useState<string | null>(null);
  const [reportDetails, setReportDetails] = useState<Record<string, ScanReport>>({});
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null);

  const loadReports = async () => {
    try {
      setLoading(true);
      const data = await getReports();
      setReports(data);
    } catch (err) {
      console.error('Failed to load scan history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const toggleReport = async (reportId: string) => {
    if (expandedReportId === reportId) {
      setExpandedReportId(null);
      return;
    }

    setExpandedReportId(reportId);

    if (!reportDetails[reportId]) {
      try {
        setLoadingDetailId(reportId);
        const detail = await getReportById(reportId);
        setReportDetails((prev) => ({ ...prev, [reportId]: detail }));
      } catch (err) {
        console.error('Failed to load report detail:', err);
      } finally {
        setLoadingDetailId(null);
      }
    }
  };

  const formatDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoStr;
    }
  };

  return (
    <>
      <Header
        title="Audit Log &amp; History"
        subtitle="Complete chronological timeline of documentation verification runs"
        onScanComplete={loadReports}
      />

      <main className="p-6 space-y-6 flex-1 overflow-y-auto max-w-6xl w-full mx-auto">
        {/* Banner summary */}
        <div className="bg-card border border-border p-4 sm:p-5 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-xs font-semibold text-white uppercase tracking-wider font-mono flex items-center space-x-2">
              <History className="w-4 h-4 text-zinc-400" />
              <span>Audit Log &amp; Verification Stream</span>
            </h2>
            <p className="text-xs text-zinc-400">
              Deterministic record of pull request scans, commits, and manual audits across monitored repositories.
            </p>
          </div>
          <div className="text-xs font-mono text-zinc-300 bg-black px-3 py-1.5 rounded border border-border w-fit shrink-0">
            <span>{reports.length} Recorded Runs</span>
          </div>
        </div>

        {/* History List */}
        {loading ? (
          <div className="bg-card border border-border p-12 rounded-xl text-center text-sm text-zinc-500 font-mono">
            Loading audit history...
          </div>
        ) : reports.length === 0 ? (
          <div className="bg-card border border-border p-12 rounded-xl text-center space-y-3">
            <div className="h-10 w-10 rounded-full bg-zinc-900 text-zinc-400 mx-auto flex items-center justify-center border border-zinc-800">
              <History className="w-5 h-5" />
            </div>
            <h3 className="text-sm font-semibold text-white">No Scan History Available</h3>
            <p className="text-xs text-zinc-400 max-w-sm mx-auto">
              Run a live scan or open a Pull Request on GitHub to generate documentation intelligence reports.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {reports.map((report) => {
              const isExpanded = expandedReportId === report.id;
              const detail = reportDetails[report.id];
              const isDetailLoading = loadingDetailId === report.id;
              const isClean = report.total_drifts === 0;

              return (
                <div
                  key={report.id}
                  className="bg-card border border-border hover:border-zinc-700 rounded-xl transition overflow-hidden"
                >
                  {/* Card Header Row */}
                  <div
                    onClick={() => toggleReport(report.id)}
                    className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer select-none"
                  >
                    <div className="flex items-start sm:items-center space-x-3.5">
                      <button className="text-zinc-500 hover:text-white mt-0.5 sm:mt-0">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-white" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </button>

                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-bold text-white">
                            {report.id}
                          </span>
                          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center space-x-1">
                            <GitCommit className="w-3 h-3 text-zinc-400" />
                            <span>
                              {report.base_sha}...{report.head_sha}
                            </span>
                          </span>
                          {report.pr_number && (
                            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center space-x-1">
                              <GitPullRequest className="w-3 h-3 text-zinc-400" />
                              <span>PR #{report.pr_number}</span>
                            </span>
                          )}
                        </div>
                        <div className="flex items-center space-x-2 text-xs text-zinc-400">
                          <Calendar className="w-3.5 h-3.5 text-zinc-500" />
                          <span>{formatDate(report.created_at)}</span>
                        </div>
                      </div>
                    </div>

                    {/* Status & Health Metrics */}
                    <div className="flex items-center space-x-3 sm:space-x-4 pl-7 sm:pl-0">
                      {isClean ? (
                        <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-md flex items-center space-x-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>0 Drifts (In Sync)</span>
                        </span>
                      ) : (
                        <span className="text-xs font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-2.5 py-1 rounded-md flex items-center space-x-1.5">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>{report.total_drifts} Drift{report.total_drifts !== 1 ? 's' : ''} Detected</span>
                        </span>
                      )}

                      <div className="text-right shrink-0">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                          Health
                        </div>
                        <div
                          className={`text-xs font-mono font-bold ${
                            report.health_score >= 90
                              ? 'text-emerald-400'
                              : 'text-red-400'
                          }`}
                        >
                          {report.health_score.toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Report Findings */}
                  {isExpanded && (
                    <div className="border-t border-border bg-black/50 p-5 space-y-4">
                      {isDetailLoading ? (
                        <div className="text-xs font-mono text-zinc-500 py-4 text-center">
                          Retrieving report findings and evidence...
                        </div>
                      ) : detail && detail.findings && detail.findings.length > 0 ? (
                        <div className="space-y-3">
                          <div className="text-[11px] font-mono uppercase tracking-wider text-zinc-400">
                            Findings Detected in this Audit:
                          </div>
                          {detail.findings.map((f) => (
                            <div
                              key={f.id}
                              className="bg-card border border-border p-4 rounded-lg space-y-3"
                            >
                              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-2.5">
                                <div className="space-y-0.5">
                                  <div className="flex items-center space-x-2">
                                    <span className="font-mono text-xs font-bold text-white">
                                      {f.changed_symbol}
                                    </span>
                                    <span className="text-[11px] font-mono text-zinc-500">
                                      in {f.doc_file}:{f.doc_start_line}
                                    </span>
                                  </div>
                                  <p className="text-xs text-zinc-400">
                                    {f.explanation}
                                  </p>
                                </div>
                                <div className="flex items-center space-x-2">
                                  {f.is_fixed === 1 ? (
                                    <span className="text-[11px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded flex items-center space-x-1">
                                      <Check className="w-3 h-3" />
                                      <span>Resolved</span>
                                    </span>
                                  ) : (
                                    <span className="text-[11px] font-mono text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded">
                                      Active Drift
                                    </span>
                                  )}
                                  <span className="text-[11px] font-mono text-zinc-400 px-2 py-0.5 bg-zinc-900 border border-zinc-800 rounded">
                                    {Math.round(f.confidence * 100)}% Confidence
                                  </span>
                                </div>
                              </div>

                              {f.outdated_excerpt && (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                                    Outdated Text:
                                  </span>
                                  <div className="font-mono text-xs text-red-400 bg-red-950/20 p-2.5 rounded border border-red-500/20">
                                    {f.outdated_excerpt}
                                  </div>
                                </div>
                              )}

                              {f.suggested_fix && (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                                    Suggested Correction:
                                  </span>
                                  <div className="font-mono text-xs text-emerald-400 bg-emerald-950/20 p-2.5 rounded border border-emerald-500/20">
                                    {f.suggested_fix}
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-xs font-mono text-zinc-400 py-3 flex items-center space-x-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span>No documentation drift or contradictions were found in this revision.</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </>
  );
}
