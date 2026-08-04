import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AdminApiError } from '../api/adminApi';
import { useAuth } from '../auth/AuthContext';
import { safeReturnLocation } from '../routing';
import { FullPageStatus } from './FullPageStatus';

export function LoginPage({
  forcedPending = false,
  forcedError,
}: {
  forcedPending?: boolean;
  forcedError?: string;
}) {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(forcedError ?? '');
  const emailRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  if (auth.state === 'loading') {
    return (
      <FullPageStatus
        title="Restoring your session"
        message="Checking your administrator session…"
      />
    );
  }
  if (auth.state === 'error') {
    return (
      <FullPageStatus
        title="Unable to restore your session"
        message="The backend could not be reached. Your session has not been classified as signed out."
        action={{ label: 'Try again', onClick: auth.retry }}
      />
    );
  }
  if (auth.state === 'authenticated') {
    return (
      <Navigate
        to={safeReturnLocation(new URLSearchParams(location.search).get('returnTo'))}
        replace
      />
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || forcedPending) return;
    if (!email.trim()) {
      setError('Enter your email address.');
      emailRef.current?.focus();
      return;
    }
    if (!password) {
      setError('Enter your password.');
      return;
    }

    setPending(true);
    setError('');
    try {
      await auth.login(email, password);
      navigate(safeReturnLocation(new URLSearchParams(location.search).get('returnTo')), {
        replace: true,
      });
    } catch (reason) {
      setPassword('');
      setError(
        reason instanceof AdminApiError && reason.kind === 'invalid_credentials'
          ? 'The email or password is invalid.'
          : reason instanceof AdminApiError && reason.kind === 'throttled'
            ? 'Too many login attempts. Please try again later.'
            : 'We could not sign you in. Check your connection and try again.',
      );
    } finally {
      setPending(false);
    }
  }

  const busy = pending || forcedPending;
  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            R
          </span>
          <span>Redmoor</span>
        </div>
        <p className="eyebrow">Administration</p>
        <h1 id="login-title">Welcome back</h1>
        <p>Sign in to manage Redmoor’s assistant services.</p>
        {error && (
          <div className="alert" role="alert" tabIndex={-1} ref={errorRef}>
            {error}
          </div>
        )}
        <form onSubmit={submit} noValidate>
          <label htmlFor="email">Email address</label>
          <input
            ref={emailRef}
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            aria-invalid={error.includes('email') || undefined}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </section>
      <aside className="login-art" aria-hidden="true">
        <div>
          <p>REDMOOR</p>
          <strong>
            Intelligence,
            <br />
            made useful.
          </strong>
        </div>
      </aside>
    </main>
  );
}
