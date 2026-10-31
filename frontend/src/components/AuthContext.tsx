'use client';

import { createContext, useContext } from 'react';
import { AuthStatus } from '@/lib/api';

export const AuthContext = createContext<AuthStatus | null>(null);

export function useAuth(): AuthStatus | null {
  return useContext(AuthContext);
}

// A portal keeps working from GitHub's data, so server-side fixes only exist in local mode.
export function isPortal(auth: AuthStatus | null): boolean {
  return Boolean(auth?.login_enabled && auth.logged_in);
}
