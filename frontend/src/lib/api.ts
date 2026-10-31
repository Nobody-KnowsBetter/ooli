export interface OverviewData {
  repository_count: number;
  avg_health_score: number;
  total_active_drifts: number;
  confirmed_drifts: number;
  possible_drifts: number;
  resolved_drifts: number;
  prs_checked: number;
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
  description?: string;
  language?: string;
  is_private?: number;
  pushed_at?: string;
  open_prs?: number;
  open_issues?: number;
  prs_checked?: number;
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
  engine?: string;
  pr_title?: string | null;
  head_sha?: string;
  default_branch?: string;
}

export interface AutoFixProposal {
  issue_id: string;
  repo_id: string;
  pr_number: number | null;
  default_branch: string;
  head_sha: string;
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
  };
  system: {
    github_token_configured: boolean;
    github_webhook_secret_configured: boolean;
    model: string;
    ollama_running: boolean;
    model_ready: boolean;
    model_problem: string;
    environment: string;
  };
}

export interface Health {
  ai_provider: string;
  model: string;
  ollama_running: boolean;
  model_ready: boolean;
  model_problem: string;
}

export interface ScanResult {
  report_id: string;
  repo_id: string;
  changes_checked: number;
  total_drifts: number;
  confirmed_drifts: number;
  possible_drifts: number;
  health_score: number;
}

// "No drift" means something different when there was no code change to check.
export function describeScan(result: ScanResult, target: string): string {
  if (result.total_drifts > 0) {
    return `${result.total_drifts} drift${result.total_drifts === 1 ? '' : 's'} found in ${target}. See Issues.`;
  }
  if (result.changes_checked === 0) {
    return `Nothing to check: ${target} has no user-facing Python changes we can analyze.`;
  }
  return `No drift: checked ${result.changes_checked} code change${result.changes_checked === 1 ? '' : 's'} in ${target}.`;
}

export interface AuthStatus {
  login_enabled: boolean;
  private_repos_allowed: boolean;
  logged_in: boolean;
  user: { login: string; name: string; avatar_url: string } | null;
  can_read_private: boolean;
}

export interface SyncStatus {
  state: 'idle' | 'syncing';
  repos: number;
  prs_scanned: number;
  errors: string[];
  last_synced_at: string | null;
}

export interface PullRequest {
  number: number;
  title: string;
  state: string;
  author: string;
}

const API_BASE = '/api';
const SELECTED_REPO_KEY = 'docguard.selectedRepo';

// Shows the backend's own message, which says what to fix.
async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${API_BASE}/auth/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Backend is not reachable');
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: 'POST' });
}

export async function getSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${API_BASE}/sync/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Could not read the sync status');
  return res.json();
}

export async function startSync(): Promise<void> {
  const res = await fetch(`${API_BASE}/sync`, { method: 'POST' });
  if (!res.ok) throw new Error('Could not start a sync');
}

// Where to read a sentence on GitHub, and where to fix it in GitHub's own editor.
export function githubFileLinks(
  repo: string | undefined,
  file: string,
  line: number,
  commit?: string,
  branch?: string
): { view: string; edit: string } | null {
  if (!repo) return null;
  const path = file.split('/').map(encodeURIComponent).join('/');
  return {
    view: `https://github.com/${repo}/blob/${commit || branch || 'HEAD'}/${path}#L${line}`,
    edit: `https://github.com/${repo}/edit/${branch || 'HEAD'}/${path}`,
  };
}

export async function getPullRequests(repo: string): Promise<PullRequest[]> {
  const res = await fetch(`${API_BASE}/github/pulls?repo=${encodeURIComponent(repo)}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(await errorMessage(res, 'Could not load pull requests'));
  return res.json();
}

export function getSelectedRepo(): string | null {
  try {
    return localStorage.getItem(SELECTED_REPO_KEY);
  } catch {
    return null;
  }
}

export function setSelectedRepo(repoId: string): void {
  try {
    localStorage.setItem(SELECTED_REPO_KEY, repoId);
    window.dispatchEvent(new Event('docguard-repo-changed'));
  } catch {
    // Without storage, scans use the default repository.
  }
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE}/health`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Backend is not reachable');
  return res.json();
}

export async function addRepository(repository: string): Promise<Repository> {
  const res = await fetch(`${API_BASE}/repositories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, 'Could not add repository'));
  return res.json();
}

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

export async function triggerLiveScan(options: { repoId?: string | null; prNumber?: number } = {}): Promise<ScanResult> {
  const repoId = options.repoId ?? getSelectedRepo();
  const res = await fetch(`${API_BASE}/scan/live`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...(repoId ? { repo_id: repoId } : {}),
      ...(options.prNumber ? { pr_number: options.prNumber } : {}),
    }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, 'Scan failed'));
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

