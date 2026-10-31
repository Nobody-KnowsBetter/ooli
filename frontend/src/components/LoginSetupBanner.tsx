'use client';

const CALLBACK_URL = 'http://localhost:3000/api/auth/callback';
const NEW_APP_URL =
  'https://github.com/settings/applications/new?' +
  new URLSearchParams({
    'oauth_application[name]': 'DocGuard (local)',
    'oauth_application[url]': 'http://localhost:3000',
    'oauth_application[callback_url]': CALLBACK_URL,
  }).toString();

// Without this setup the portal features stay hidden, so say so instead of leaving people guessing.
export function LoginSetupBanner() {
  return (
    <aside className="m-6 mb-0 bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 text-xs text-zinc-800 space-y-2">
      <h2 className="font-semibold text-sm text-ink">GitHub sign-in isn&apos;t set up yet</h2>
      <p>
        You&apos;re in local mode, so sign-in, your repository list, auto-sync and sign-out are hidden. Turning them on
        takes two steps:
      </p>
      <ol className="list-decimal pl-4 space-y-1">
        <li>
          <a href={NEW_APP_URL} target="_blank" rel="noreferrer" className="underline font-medium">
            Create a GitHub OAuth App
          </a>{' '}
          with the callback URL <code className="font-mono">{CALLBACK_URL}</code>, then generate a client secret.
        </li>
        <li>
          In a terminal at the project folder, run <code className="font-mono">./scripts/setup-github-login.sh</code>{' '}
          and paste the two values. Then reload this page. No restart needed.
        </li>
      </ol>
    </aside>
  );
}
