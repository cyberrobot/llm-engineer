import { useEffect, useState, type ReactNode } from 'react';
import { getCurrentAdministrator } from '../services/getCurrentAdministrator';

type AuthenticationState = 'checking' | 'authenticated' | 'unauthenticated';

export default function AuthenticatedRagBoundary({
  children,
}: {
  children: ReactNode;
}) {
  const [state, setState] = useState<AuthenticationState>('checking');

  useEffect(() => {
    let active = true;
    getCurrentAdministrator()
      .then(() => {
        if (active) setState('authenticated');
      })
      .catch(() => {
        if (active) setState('unauthenticated');
      });

    return () => {
      active = false;
    };
  }, []);

  if (state === 'checking') {
    return <main className="p-5">Checking administrator session…</main>;
  }

  if (state === 'unauthenticated') {
    return (
      <main className="p-5">
        <h1>Administrator authentication required</h1>
        <p className="mt-3 text-text">
          Sign in through the administrator application, then reload this page.
        </p>
      </main>
    );
  }

  return children;
}
