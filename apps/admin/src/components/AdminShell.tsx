import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const links = [
  ['/admin', 'Dashboard'],
  ['/admin/assistants', 'Assistants'],
  ['/admin/knowledge-sources', 'Knowledge Sources'],
] as const;

function titleFor(pathname: string) {
  if (pathname.startsWith('/admin/assistants')) {
    if (pathname.includes('/knowledge/') && pathname.endsWith('/new')) return 'Add knowledge source';
    if (pathname.includes('/knowledge/')) return 'Knowledge source details';
    if (pathname.endsWith('/knowledge')) return 'Knowledge & retrieval';
    if (pathname.endsWith('/new')) return 'Create assistant';
    if (pathname.endsWith('/edit')) return 'Edit assistant';
    return 'Assistants';
  }
  return links.find(([path]) => path === pathname)?.[1] ?? 'Page not found';
}

export function AdminShell() {
  const auth = useAuth();
  const user = auth.user!;
  const navigate = useNavigate();
  const location = useLocation();
  const heading = useRef<HTMLHeadingElement>(null);
  const [open, setOpen] = useState(false);
  const pageTitle = titleFor(location.pathname);

  useEffect(() => {
    heading.current?.focus();
  }, [location.pathname]);

  async function logout() {
    try {
      await auth.logout();
    } catch {
      // The provider still clears stale frontend auth state.
    } finally {
      navigate('/login', { replace: true });
    }
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            R
          </span>
          <span>
            Redmoor <small>Admin</small>
          </span>
        </div>
        <button
          className="menu-button"
          aria-expanded={open}
          aria-controls="primary-nav"
          onClick={() => setOpen(!open)}
        >
          Menu
        </button>
        <div className="identity">
          <span>{user.email}</span>
          <button className="secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <nav id="primary-nav" aria-label="Primary" className={open ? 'open' : ''}>
        {links.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/admin'}
            onClick={() => setOpen(false)}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <main id="main">
        <h1 tabIndex={-1} ref={heading}>
          {pageTitle}
        </h1>
        <Outlet />
      </main>
    </div>
  );
}
