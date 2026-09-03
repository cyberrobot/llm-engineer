import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

type IconName =
  | 'activity'
  | 'assistants'
  | 'cache'
  | 'dashboard'
  | 'health'
  | 'jobs'
  | 'knowledge'
  | 'maintenance'
  | 'overview';
type NavigationItem = {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
};

const primaryLinks: readonly NavigationItem[] = [
  { to: '/admin', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/admin/assistants', label: 'Assistants', icon: 'assistants' },
  {
    to: '/admin/knowledge-sources',
    label: 'Knowledge Sources',
    icon: 'knowledge',
  },
];
const operationsLinks: readonly NavigationItem[] = [
  { to: '/admin/operations', label: 'Overview', icon: 'overview', end: true },
  { to: '/admin/operations/health', label: 'Health', icon: 'health' },
  { to: '/admin/operations/jobs', label: 'Jobs', icon: 'jobs' },
  { to: '/admin/operations/cache', label: 'Cache', icon: 'cache' },
  {
    to: '/admin/operations/maintenance',
    label: 'Maintenance',
    icon: 'maintenance',
  },
];
const auditLink: NavigationItem = {
  to: '/admin/operations/audit',
  label: 'Audit & Activity',
  icon: 'activity',
};
const mobileQuery = '(max-width: 1023px)';

function titleFor(pathname: string) {
  if (pathname.startsWith('/admin/operations')) {
    if (pathname.startsWith('/admin/operations/jobs/'))
      return 'Operational job details';
    if (pathname.startsWith('/admin/operations/audit/'))
      return 'Audit entry details';
    if (pathname.endsWith('/health')) return 'Health diagnostics';
    if (pathname.endsWith('/cache')) return 'Cache operations';
    if (pathname.endsWith('/maintenance')) return 'Maintenance mode';
    if (pathname.endsWith('/jobs')) return 'Operational jobs';
    if (pathname.endsWith('/audit')) return 'Administrative audit';
    return 'Operations';
  }
  if (pathname.startsWith('/admin/assistants')) {
    if (pathname.includes('/knowledge/') && pathname.endsWith('/new'))
      return 'Add knowledge source';
    if (pathname.includes('/knowledge/')) return 'Knowledge source details';
    if (pathname.endsWith('/knowledge')) return 'Knowledge & retrieval';
    if (pathname.endsWith('/behaviour')) return 'Assistant behaviour';
    if (pathname.endsWith('/preview')) return 'Assistant preview';
    if (pathname.endsWith('/new')) return 'Create assistant';
    if (pathname.endsWith('/edit')) return 'Edit assistant';
    return 'Assistants';
  }
  return (
    primaryLinks.find(({ to }) => to === pathname)?.label ?? 'Page not found'
  );
}

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    assistants: (
      <>
        <circle cx="9" cy="8" r="4" />
        <path d="M2.5 21a6.5 6.5 0 0 1 13 0M16 4.5a4 4 0 0 1 0 7M18 15a6 6 0 0 1 3.5 6" />
      </>
    ),
    knowledge: (
      <>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v17H6.5A2.5 2.5 0 0 0 4 22.5z" />
        <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v17h4.5a2.5 2.5 0 0 1 2.5 2.5z" />
      </>
    ),
    overview: (
      <>
        <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
      </>
    ),
    health: (
      <>
        <path d="M3 12h4l2.5-6 5 12 2.5-6h4" />
      </>
    ),
    jobs: (
      <>
        <rect x="4" y="5" width="16" height="16" rx="2" />
        <path d="M8 5V3M16 5V3M8 10h8M8 15h5" />
      </>
    ),
    cache: (
      <>
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </>
    ),
    maintenance: (
      <>
        <path d="M14.5 6.5a4 4 0 0 0-5-5L12 4 8 8 5.5 5.5a4 4 0 0 0 5 5L19 19a2.1 2.1 0 0 0 3-3z" />
      </>
    ),
    activity: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2M3 12H1M23 12h-2" />
      </>
    ),
  };
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5 shrink-0"
    >
      {paths[name]}
    </svg>
  );
}

const linkClasses = ({ isActive }: { isActive: boolean }) =>
  [
    'group flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-shell-focus',
    isActive
      ? 'bg-shell-active font-bold text-white'
      : 'text-shell-nav-muted hover:bg-shell-hover hover:text-white',
  ].join(' ');

function Brand() {
  return (
    <div className="flex min-w-0 items-center gap-3 text-white">
      <span
        aria-hidden="true"
        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-shell-accent font-serif text-xl font-bold text-shell-nav"
      >
        A
      </span>
      <span className="min-w-0 leading-tight">
        <strong className="block truncate text-base">Assistant Platform</strong>
        <small className="text-xs font-medium tracking-wide text-shell-nav-muted">
          Redmoor Admin
        </small>
      </span>
    </div>
  );
}

function NavigationLink({
  item,
  onNavigate,
}: {
  item: NavigationItem;
  onNavigate: () => void;
}) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={linkClasses}
    >
      <Icon name={item.icon} />
      <span>{item.label}</span>
    </NavLink>
  );
}

function Sidebar({
  email,
  onLogout,
  onNavigate,
  mobile = false,
}: {
  email: string;
  onLogout: () => void;
  onNavigate: () => void;
  mobile?: boolean;
}) {
  const { pathname } = useLocation();
  const operationsActive = pathname.startsWith('/admin/operations');
  return (
    <aside
      className={
        mobile
          ? 'fixed inset-y-0 left-0 z-50 flex w-[min(20rem,calc(100vw-2rem))] flex-col overflow-y-auto bg-shell-nav text-white shadow-2xl'
          : 'sticky top-0 hidden h-screen w-64 flex-col overflow-y-auto bg-shell-nav text-white lg:flex'
      }
    >
      <div className="border-b border-white/10 px-5 py-6">
        <Brand />
      </div>
      <nav
        id="primary-nav"
        aria-label="Primary"
        className="flex-1 space-y-6 px-3 py-5"
      >
        <div className="space-y-1">
          {primaryLinks.map((item) => (
            <NavigationLink key={item.to} item={item} onNavigate={onNavigate} />
          ))}
        </div>
        <div>
          <div
            aria-current={operationsActive ? 'true' : undefined}
            className={
              operationsActive
                ? 'mb-2 px-4 text-xs font-bold uppercase tracking-[0.16em] text-shell-accent'
                : 'mb-2 px-4 text-xs font-bold uppercase tracking-[0.16em] text-shell-nav-muted'
            }
          >
            Operations
          </div>
          <div className="space-y-1 border-l border-white/15 pl-2">
            {operationsLinks.map((item) => (
              <NavigationLink
                key={item.to}
                item={item}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </div>
        <NavigationLink item={auditLink} onNavigate={onNavigate} />
      </nav>
      <div className="border-t border-white/10 p-4">
        <div className="mb-3 min-w-0 px-2">
          <span
            className="block truncate text-sm font-semibold text-white"
            title={email}
          >
            {email}
          </span>
          <span className="mt-0.5 block text-xs text-shell-nav-muted">
            Platform Administrator
          </span>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center justify-center rounded-lg border border-white/25 bg-transparent px-3 py-2 text-sm font-bold text-white transition-colors hover:bg-shell-hover focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-shell-focus"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}

function useMobileLayout(setOpen: Dispatch<SetStateAction<boolean>>) {
  const [mobile, setMobile] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia(mobileQuery).matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(mobileQuery);
    const update = (event: MediaQueryListEvent) => {
      setMobile(event.matches);
      if (!event.matches) setOpen(false);
    };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, [setOpen]);
  return mobile;
}

export function AdminShell({
  initialMenuOpen = false,
  layout = 'responsive',
}: {
  initialMenuOpen?: boolean;
  layout?: 'desktop' | 'mobile' | 'responsive';
}) {
  const auth = useAuth();
  const user = auth.user!;
  const navigate = useNavigate();
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const heading = useRef<HTMLHeadingElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(initialMenuOpen);
  const responsiveMobile = useMobileLayout(setOpen);
  const mobile =
    layout === 'mobile' || (layout === 'responsive' && responsiveMobile);
  const pageTitle = titleFor(location.pathname);

  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      setOpen(false);
      previousPath.current = location.pathname;
    }
    heading.current?.focus();
  }, [location.pathname]);
  useEffect(() => {
    if (!mobile || !open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobile, open]);

  async function logout() {
    try {
      await auth.logout();
    } catch {
      /* The provider still clears stale frontend auth state. */
    } finally {
      navigate('/login', { replace: true });
    }
  }

  return (
    <div className="min-h-screen min-w-0 bg-shell-canvas text-shell-text lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <a
        className="fixed left-4 top-[-5rem] z-[60] rounded-md bg-white px-4 py-3 font-bold text-shell-nav shadow-lg focus:top-4 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-shell-focus"
        href="#main"
      >
        Skip to main content
      </a>
      {!mobile && (
        <Sidebar
          email={user.email}
          onLogout={logout}
          onNavigate={() => setOpen(false)}
        />
      )}
      {mobile && (
        <>
          <header className="sticky top-0 z-30 flex min-h-16 items-center justify-between gap-3 border-b border-shell-border bg-shell-nav px-4 shadow-sm">
            <Brand />
            <button
              ref={menuButton}
              type="button"
              aria-expanded={open}
              aria-controls="primary-nav"
              aria-label={open ? 'Close navigation' : 'Open navigation'}
              onClick={() => setOpen((value) => !value)}
              className="grid h-12 w-12 shrink-0 place-items-center justify-center rounded-lg border border-white/25 bg-transparent text-white hover:bg-shell-hover focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-shell-focus"
            >
              <svg
                aria-hidden="true"
                focusable="false"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                className="h-6 w-6"
              >
                {open ? (
                  <path d="M6 6l12 12M18 6 6 18" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" />
                )}
              </svg>
            </button>
          </header>
          {open && (
            <button
              type="button"
              tabIndex={-1}
              aria-label="Close navigation overlay"
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 cursor-default rounded-none bg-black/55 p-0"
            />
          )}
          <div hidden={!open}>
            <Sidebar
              mobile
              email={user.email}
              onLogout={logout}
              onNavigate={() => setOpen(false)}
            />
          </div>
        </>
      )}
      <main
        id="main"
        inert={mobile && open ? true : undefined}
        className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-10 xl:px-14"
      >
        <h1
          tabIndex={-1}
          ref={heading}
          className="mt-0 mb-8 font-serif text-3xl leading-tight font-bold text-shell-heading outline-none sm:text-4xl lg:text-5xl focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-shell-focus"
        >
          {pageTitle}
        </h1>
        <Outlet />
      </main>
    </div>
  );
}
