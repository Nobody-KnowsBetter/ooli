export interface OverviewData {
  repository_count: number;
  avg_health_score: number;
  total_active_drifts: number;
  confirmed_drifts: number;
  possible_drifts: number;
  resolved_drifts: number;
  recent_reports: Array<{
    id: string;
    repo_id: string;
    base_sha: string;
    head_sha: string;
    pr_number: number | null;
    status: string;
    total_drifts: number;
    health_score: number;
    created_at: string;
  }>;
  recent_issues: Issue[];
}

export interface Repository {
  id: string;
  full_name: string;
  default_branch: string;
  health_score: number;
  last_scanned_at: string;
}

export interface Issue {
  id: string;
  report_id: string;
  repo_id?: string;
  pr_number?: number | null;
  verdict: 'CONFIRMED_DRIFT' | 'POSSIBLE_DRIFT' | 'NO_DRIFT_DETECTED';
  confidence: number;
  source_file: string;
  changed_symbol: string;
  doc_file: string;
  doc_start_line: number;
  doc_end_line: number;
  outdated_excerpt: string;
  explanation: string;
  suggested_fix: string;
  code_diff?: string;
  evidence?: string[];
  is_fixed: number;
  created_at: string;
  diff_preview?: string;
  is_applicable?: boolean;
}

export interface AutoFixProposal {
  issue_id: string;
  changed_symbol: string;
  source_file: string;
  doc_file: string;
  doc_start_line: number;
  outdated_excerpt: string;
  suggested_fix: string;
  diff: string;
  is_applicable: boolean;
  confidence: number;
  verdict: string;
}

export interface ScanReport {
  id: string;
  repo_id: string;
  base_sha: string;
  head_sha: string;
  pr_number: number | null;
  status: string;
  total_drifts: number;
  confirmed_drifts: number;
  possible_drifts: number;
  health_score: number;
  created_at: string;
  findings?: Issue[];
}

export interface SettingsData {
  settings: {
    ai_provider: string;
    confidence_threshold: string;
    auto_comment: string;
    github_app_name: string;
    github_installation_status: string;
    monitored_branches: string;
  };
  system: {
    github_token_configured: boolean;
    github_webhook_secret_configured: boolean;
    gemini_api_key_configured: boolean;
    openai_api_key_configured: boolean;
    environment: string;
  };
}

const API_BASE = '/api';

export async function getOverview(): Promise<OverviewData> {
  const res = await fetch(`${API_BASE}/overview`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch overview data');
  return res.json();
}

export async function getRepositories(): Promise<Repository[]> {
  const res = await fetch(`${API_BASE}/repositories`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch repositories');
  return res.json();
}

export async function getIssues(status?: string, verdict?: string): Promise<Issue[]> {
  const params = new URLSearchParams();
  if (status) params.append('status', status);
  if (verdict) params.append('verdict', verdict);
  const url = `${API_BASE}/issues?${params.toString()}`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch issues');
  return res.json();
}

export async function getIssueById(id: string): Promise<Issue> {
  const res = await fetch(`${API_BASE}/issues/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch issue details');
  return res.json();
}

export async function applyFixForIssue(issueId: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/issues/${encodeURIComponent(issueId)}/fix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error('Failed to apply fix');
  return res.json();
}

export async function getAutoFixProposals(): Promise<AutoFixProposal[]> {
  const res = await fetch(`${API_BASE}/autofix/proposals`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch auto-fix proposals');
  return res.json();
}

export async function triggerLiveScan(baseRef: string = 'HEAD~1', headRef: string = 'HEAD'): Promise<any> {
  const res = await fetch(`${API_BASE}/scan/live`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_ref: baseRef, head_ref: headRef }),
  });
  if (!res.ok) throw new Error('Scan failed');
  return res.json();
}

export async function getSettings(): Promise<SettingsData> {
  const res = await fetch(`${API_BASE}/settings`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch settings');
  return res.json();
}

export async function getReports(): Promise<ScanReport[]> {
  const res = await fetch(`${API_BASE}/reports`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch reports');
  return res.json();
}

export async function getReportById(id: string): Promise<ScanReport> {
  const res = await fetch(`${API_BASE}/reports/${encodeURIComponent(id)}`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to fetch report details');
  return res.json();
}

export async function updateSettings(updates: Partial<SettingsData['settings']>): Promise<any> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error('Failed to update settings');
  return res.json();
}

