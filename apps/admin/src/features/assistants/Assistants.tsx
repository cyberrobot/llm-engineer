import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import {
  Link,
  unstable_usePrompt as usePrompt,
  useBeforeUnload,
  useNavigate,
  useParams,
} from 'react-router-dom';
import {
  AdminApiError,
  type Assistant,
  type AssistantDetail,
  type AssistantStatus,
  type AssistantVisibility,
} from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';
import { AssistantNavigation } from './AssistantBehaviour';

function message(error: unknown) {
  if (!(error instanceof AdminApiError))
    return 'The request could not be completed.';
  if (error.kind === 'network')
    return 'The backend could not be reached. Try again.';
  if (error.kind === 'server')
    return 'The server could not complete the request. Try again.';
  if (error.kind === 'invalid_response')
    return 'The backend returned an invalid response.';
  if (error.kind === 'forbidden')
    return 'You do not have permission to perform this action.';
  return 'The request could not be completed.';
}
function useSessionError(error: unknown) {
  const auth = useAuth();
  useEffect(() => {
    if (error instanceof AdminApiError && error.kind === 'unauthenticated')
      auth.sessionExpired();
  }, [auth, error]);
}
export function Badge({
  value,
}: {
  value: AssistantStatus | AssistantVisibility;
}) {
  return (
    <span className={`badge badge-${value}`}>
      {value[0].toUpperCase() + value.slice(1)}
    </span>
  );
}

function initialsFor(name: string): string {
  const words = name.replace(/[^A-Za-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '·';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function IdentityTile({ name }: { name: string }) {
  const initials = useMemo(() => initialsFor(name), [name]);
  return (
    <span aria-hidden="true" className="assistant-identity-tile">
      {initials}
    </span>
  );
}

function statusIcon(value: AssistantStatus | AssistantVisibility) {
  if (value === 'active') {
    return (
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
      </svg>
    );
  }
  if (value === 'inactive') {
    return (
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="12" r="4" />
      </svg>
    );
  }
  if (value === 'public') {
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
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
      </svg>
    );
  }
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
    >
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

function BadgeWithIcon({
  value,
  Icon,
}: {
  value: AssistantStatus | AssistantVisibility;
  Icon: ReactNode;
}) {
  return (
    <span className={`badge assistants-badge-with-icon badge-${value}`}>
      <span aria-hidden="true" className="assistants-badge-icon">
        {Icon}
      </span>
      {value[0].toUpperCase() + value.slice(1)}
    </span>
  );
}

export function AssistantsPage() {
  const { api } = useAuth();
  const [page, setPage] = useState<{
    items: Assistant[];
    total: number;
    limit: number;
    offset: number;
  } | null>(null);
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  const [refreshAttempt, setRefreshAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const refreshPendingRef = useRef(false);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<AssistantStatus | ''>('');
  const [visibilityFilter, setVisibilityFilter] = useState<AssistantVisibility | ''>('');
  const [action, setAction] = useState<{ assistant: Assistant; intent: 'status' | 'delete' } | undefined>();
  const [notice, setNotice] = useState('');
  const noticeRef = useRef<HTMLParagraphElement>(null);
  useSessionError(error);
  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);
  useEffect(() => {
    const controller = new AbortController();
    const manualRefresh = refreshPendingRef.current;
    api
      .listAssistants(
        {
          limit: 50,
          offset,
          status: statusFilter || undefined,
          visibility: visibilityFilter || undefined,
        },
        controller.signal,
      )
      .then((result) => {
        if (result.items.length === 0 && offset > 0 && offset >= result.total) {
          setOffset(result.total === 0 ? 0 : Math.floor((result.total - 1) / result.limit) * result.limit);
          return;
        }
        setError(undefined);
        setPage(result);
      })
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e);
      })
      .finally(() => {
        if (manualRefresh) {
          refreshPendingRef.current = false;
          setRefreshing(false);
        }
      });
    return () => controller.abort();
  }, [api, attempt, offset, refreshAttempt, statusFilter, visibilityFilter]);
  function refresh() {
    if (refreshPendingRef.current) return;
    refreshPendingRef.current = true;
    setRefreshing(true);
    setError(undefined);
    setRefreshAttempt((value) => value + 1);
  }
  if (error)
    return (
      <section className="feature assistants-collection">
        <PageIntroduction refreshing={refreshing} onRefresh={refresh} />
        <State
          title="Unable to load assistants"
          text={message(error)}
          action={() => {
            setError(undefined);
            setPage(null);
            setAttempt((x) => x + 1);
          }}
        />
      </section>
    );
  if (!page) {
    return (
      <section className="feature">
        <PageIntroduction refreshing={refreshing} onRefresh={refresh} />
        <p role="status">Loading assistants…</p>
      </section>
    );
  }
  return (
    <section className="feature assistants-collection">
      <PageIntroduction refreshing={refreshing} onRefresh={refresh} />
      <SummaryCards items={page.items} total={page.total} />
      <Filters
        statusFilter={statusFilter}
        visibilityFilter={visibilityFilter}
        onStatusFilter={(value) => {
          setPage(null);
          setOffset(0);
          setStatusFilter(value);
        }}
        onVisibilityFilter={(value) => {
          setPage(null);
          setOffset(0);
          setVisibilityFilter(value);
        }}
        resultCount={page.total}
      />
      {notice && (
        <p ref={noticeRef} tabIndex={-1} className="success" role="status">
          {notice}
        </p>
      )}
      {page.items.length === 0 && page.total === 0 ? (
        <div className="empty assistants-empty">
          {statusFilter || visibilityFilter ? (
            <>
              <h2>No matching assistants</h2>
              <p>Clear the filters to view all assistants.</p>
              <button
                onClick={() => {
                  setPage(null);
                  setOffset(0);
                  setStatusFilter('');
                  setVisibilityFilter('');
                }}
              >
                Clear filters
              </button>
            </>
          ) : (
            <>
              <h2>No assistants yet</h2>
              <p>Create the first assistant to get started.</p>
              <Link className="button" to="/admin/assistants/new">
                New Assistant
              </Link>
            </>
          )}
        </div>
      ) : (
        <AssistantsTable
          items={page.items}
          activeAssistantId={action?.assistant.id}
          onAction={setAction}
        />
      )}
      {page.total > page.limit && (
        <nav className="pagination" aria-label="Assistants pages">
          <p>
            Showing {page.offset + 1}–
            {Math.min(page.offset + page.items.length, page.total)} of {page.total}
          </p>
          <div className="actions">
            <button
              disabled={page.offset === 0}
              onClick={() => {
                setPage(null);
                setOffset(Math.max(0, page.offset - page.limit));
              }}
            >
              Previous
            </button>
            <button
              disabled={page.offset + page.items.length >= page.total}
              onClick={() => {
                setPage(null);
                setOffset(page.offset + page.limit);
              }}
            >
              Next
            </button>
          </div>
        </nav>
      )}
      {action && (
        <ActionDialog
          assistant={action.assistant}
          intent={action.intent}
          onClose={() => {
            const assistantId = action.assistant.id;
            setAction(undefined);
            requestAnimationFrame(() => {
              document
                .querySelector<HTMLButtonElement>(`[data-assistant-action-id="${assistantId}"]`)
                ?.focus();
            });
          }}
          onDone={(deleted) => {
            setAction(undefined);
            setNotice(deleted ? 'Assistant deleted. List refreshed.' : 'Assistant status updated.');
            setAttempt((x) => x + 1);
          }}
        />
      )}
    </section>
  );
}

function PageIntroduction({
  refreshing,
  onRefresh,
}: {
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="assistants-intro">
      <div className="assistants-intro-text">
        <p className="assistants-intro-lead">
          Manage identity, availability and public access for every assistant.
        </p>
      </div>
      <div className="assistants-intro-actions">
        <button
          type="button"
          className="assistants-refresh-button"
          aria-label="Refresh assistants list"
          aria-busy={refreshing}
          disabled={refreshing}
          onClick={onRefresh}
        >
          <span aria-hidden="true" className="assistants-refresh-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              focusable="false"
            >
              <path d="M21 12a9 9 0 1 1-3-6.7" />
              <path d="M21 4v5h-5" />
            </svg>
          </span>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
        <Link to="/admin/assistants/new" className="button assistants-primary-button">
          <span aria-hidden="true" className="assistants-primary-icon">
            +
          </span>
          New Assistant
        </Link>
      </div>
    </div>
  );
}

function SummaryCards({
  items,
  total,
}: {
  items: Assistant[];
  total: number;
}) {
  const active = items.filter((a) => a.status === 'active').length;
  const publicCount = items.filter((a) => a.visibility === 'public').length;
  const privateCount = items.filter((a) => a.visibility === 'private').length;
  const mostRecent = items.reduce<Assistant | null>((latest, current) => {
    const currentTime = Date.parse(current.updatedAt);
    if (!Number.isFinite(currentTime)) return latest;
    const latestTime = latest ? Date.parse(latest.updatedAt) : -Infinity;
    return currentTime > latestTime ? current : latest;
  }, null);
  return (
    <div className="assistants-summary" role="region" aria-label="Collection summary">
      <SummaryCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <circle cx="9" cy="8" r="4" />
            <path d="M2.5 21a6.5 6.5 0 0 1 13 0M16 4.5a4 4 0 0 1 0 7M18 15a6 6 0 0 1 3.5 6" />
          </svg>
        }
        label="Total"
        value={total.toString()}
        note="authoritative backend count"
      />
      <SummaryCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <path d="M5 12l5 5L20 7" />
          </svg>
        }
        label="Active"
        value={active.toString()}
        note="on this page"
      />
      <SummaryCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <circle cx="12" cy="12" r="9" />
            <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
          </svg>
        }
        label="Public"
        value={publicCount.toString()}
        note="on this page"
      />
      <SummaryCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <rect x="5" y="11" width="14" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
        }
        label="Private"
        value={privateCount.toString()}
        note="on this page"
      />
      <SummaryCard
        icon={
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
          </svg>
        }
        label="Latest update"
        value={mostRecent ? formatUpdated(mostRecent.updatedAt) : '—'}
        note={mostRecent ? `${mostRecent.name}` : 'no assistants loaded'}
        title={mostRecent ? `${mostRecent.name} — ${formatUpdatedLong(mostRecent.updatedAt)}` : undefined}
      />
    </div>
  );
}

function formatUpdated(value: string): string {
  return new Date(value).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  });
}

function formatUpdatedLong(value: string): string {
  return new Date(value).toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  });
}

function SummaryCard({
  icon,
  label,
  value,
  note,
  title,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  note: string;
  title?: string;
}) {
  return (
    <div className="assistants-summary-card" title={title}>
      <span aria-hidden="true" className="assistants-summary-icon">
        {icon}
      </span>
      <div className="assistants-summary-body">
        <p className="assistants-summary-label">{label}</p>
        <p className="assistants-summary-value">{value}</p>
        <p className="assistants-summary-note">{note}</p>
      </div>
    </div>
  );
}

function Filters({
  statusFilter,
  visibilityFilter,
  onStatusFilter,
  onVisibilityFilter,
  resultCount,
}: {
  statusFilter: AssistantStatus | '';
  visibilityFilter: AssistantVisibility | '';
  onStatusFilter: (value: AssistantStatus | '') => void;
  onVisibilityFilter: (value: AssistantVisibility | '') => void;
  resultCount: number;
}) {
  return (
    <div className="filters assistants-filters" aria-label="Filter assistants">
      <label>
        Status
        <select
          value={statusFilter}
          onChange={(event) => onStatusFilter(event.target.value as AssistantStatus | '')}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </label>
      <label>
        Visibility
        <select
          value={visibilityFilter}
          onChange={(event) => onVisibilityFilter(event.target.value as AssistantVisibility | '')}
        >
          <option value="">All visibilities</option>
          <option value="public">Public</option>
          <option value="private">Private</option>
        </select>
      </label>
      <p className="assistants-filter-count" aria-live="polite">
        {resultCount} {resultCount === 1 ? 'result' : 'results'}
      </p>
    </div>
  );
}

function AssistantsTable({
  items,
  activeAssistantId,
  onAction,
}: {
  items: Assistant[];
  activeAssistantId?: string;
  onAction: (entry: { assistant: Assistant; intent: 'status' | 'delete' }) => void;
}) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  return (
    <div className="table-wrap assistants-table-wrap">
      <table className="assistants-table">
        <thead>
          <tr>
            <th scope="col">Assistant</th>
            <th scope="col">Status</th>
            <th scope="col">Visibility</th>
            <th scope="col">Updated</th>
            <th scope="col" className="assistants-actions-column">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => {
            const isOpen = openMenu === a.id;
            const isActive = isOpen || activeAssistantId === a.id;
            const statusLabel = a.status[0].toUpperCase() + a.status.slice(1);
            const visibilityLabel = a.visibility[0].toUpperCase() + a.visibility.slice(1);
            const statusToggleLabel = a.status === 'active' ? `Deactivate ${a.name}` : `Activate ${a.name}`;
            return (
              <tr
                key={a.id}
                className={isActive ? 'assistants-row assistants-row-active' : 'assistants-row'}
              >
                <td className="assistants-identity-cell">
                  <IdentityTile name={a.name} />
                  <span className="assistants-identity-text">
                    <span className="assistants-name">{a.name}</span>
                    <span className="assistants-slug">{a.slug}</span>
                  </span>
                </td>
                <td data-label="Status">
                  <BadgeWithIcon value={a.status} Icon={statusIcon(a.status)} />
                </td>
                <td data-label="Visibility">
                  <BadgeWithIcon value={a.visibility} Icon={statusIcon(a.visibility)} />
                </td>
                <td data-label="Updated" className="assistants-updated-cell">
                  {formatUpdated(a.updatedAt)}
                </td>
                <td data-label="Actions" className="assistants-actions-cell">
                  <RowActionMenu
                    assistant={a}
                    isOpen={isOpen}
                    onOpenChange={(next) => setOpenMenu(next ? a.id : null)}
                    onChoose={(intent) => {
                      setOpenMenu(null);
                      if (intent === 'edit') return;
                      onAction({ assistant: a, intent });
                    }}
                    labels={{ statusToggleLabel, statusLabel, visibilityLabel }}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowActionMenu({
  assistant,
  isOpen,
  onOpenChange,
  onChoose,
  labels,
}: {
  assistant: Assistant;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onChoose: (intent: 'edit' | 'status' | 'delete') => void;
  labels: { statusToggleLabel: string; statusLabel: string; visibilityLabel: string };
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  useEffect(() => {
    if (!isOpen) return;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    function onPointer(event: MouseEvent) {
      const target = event.target as Node | null;
      if (!target) return;
      if (triggerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      onOpenChange(false);
    }
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      onOpenChange(false);
      triggerRef.current?.focus();
    }
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [isOpen, onOpenChange]);
  function onTriggerKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'Escape') {
      onOpenChange(false);
      triggerRef.current?.focus();
    }
    if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !isOpen) {
      event.preventDefault();
      onOpenChange(true);
    }
  }
  function onMenuKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
    );
    if (items.length === 0) return;
    const current = items.indexOf(document.activeElement as HTMLElement);
    const next = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? items.length - 1
        : event.key === 'ArrowDown'
          ? (current + 1) % items.length
          : (current <= 0 ? items.length : current) - 1;
    items[next]?.focus();
  }
  return (
    <div className="assistants-row-menu">
      <button
        ref={triggerRef}
        type="button"
        className="assistants-row-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={menuId}
        aria-label={`Actions for ${assistant.name}`}
        data-assistant-action-id={assistant.id}
        onKeyDown={onTriggerKey}
        onClick={() => onOpenChange(!isOpen)}
      >
        <span aria-hidden="true" className="assistants-row-menu-dots">
          <svg viewBox="0 0 24 24" focusable="false" fill="currentColor">
            <circle cx="6" cy="12" r="2" />
            <circle cx="12" cy="12" r="2" />
            <circle cx="18" cy="12" r="2" />
          </svg>
        </span>
      </button>
      {isOpen && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={`Actions for ${assistant.name}`}
          className="assistants-row-menu-panel"
          onKeyDown={onMenuKey}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) onOpenChange(false);
          }}
        >
          <Link
            to={`/admin/assistants/${assistant.id}/edit`}
            role="menuitem"
            className="assistants-row-menu-item"
            onClick={() => onOpenChange(false)}
          >
            Edit
          </Link>
          <button
            type="button"
            role="menuitem"
            className="assistants-row-menu-item"
            onClick={() => onChoose('status')}
          >
            {labels.statusLabel === 'Active' ? 'Deactivate' : 'Activate'}
            <span className="assistants-row-menu-item-detail">
              {labels.statusLabel === 'Active' ? 'Make unavailable' : 'Make available'}
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="assistants-row-menu-item assistants-row-menu-item-danger"
            onClick={() => onChoose('delete')}
          >
            Delete
            <span className="assistants-row-menu-item-detail">
              Permanently remove {labels.visibilityLabel.toLowerCase()} assistant
            </span>
          </button>
        </div>
      )}
      <span className="visually-hidden">{labels.statusToggleLabel}</span>
    </div>
  );
}

function State({
  title,
  text,
  action,
  link,
}: {
  title: string;
  text: string;
  action?: () => void;
  link?: { label: string; to: string };
}) {
  return (
    <section className="empty" role="alert">
      <h2>{title}</h2>
      <p>{text}</p>
      {action && <button onClick={action}>Try again</button>}
      {link && <Link to={link.to}>{link.label}</Link>}
    </section>
  );
}
function ActionDialog({
  assistant,
  intent,
  onClose,
  onDone,
}: {
  assistant: Assistant;
  intent: 'status' | 'delete';
  onClose: () => void;
  onDone: (deleted: boolean) => void;
}) {
  const auth = useAuth();
  const ref = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const deleting = intent === 'delete';
  const name = assistant.name;
  useEffect(() => ref.current?.showModal(), []);
  async function confirm() {
    setPending(true);
    setError('');
    try {
      if (deleting) await auth.api.deleteAssistant(assistant.id);
      else
        await auth.api.updateAssistant(assistant.id, {
          concurrency_token: assistant.concurrencyToken,
          status: assistant.status === 'active' ? 'inactive' : 'active',
        });
      onDone(deleting);
    } catch (e) {
      if (e instanceof AdminApiError && e.kind === 'unauthenticated') {
        auth.sessionExpired();
        return;
      }
      if (deleting && e instanceof AdminApiError && e.kind === 'not_found') {
        onDone(true);
        return;
      }
      setError(
        e instanceof AdminApiError && e.kind === 'conflict'
          ? e.code === 'assistant_has_dependencies'
            ? 'This assistant cannot be deleted while it has dependent records.'
            : e.code === 'protected_assistant'
              ? 'This seeded assistant is protected and cannot be deleted.'
            : 'The assistant changed on the server. Refresh and try again.'
          : message(e),
      );
      setPending(false);
    }
  }
  return (
    <dialog ref={ref} onCancel={onClose} aria-labelledby="dialog-title">
      <h2 id="dialog-title">
        {deleting
          ? 'Delete'
          : assistant.status === 'active'
            ? 'Deactivate'
            : 'Activate'}{' '}
        {name}?
      </h2>
      <p>
        {deleting
          ? 'Deletion is permanent and may be unavailable when dependent records exist.'
          : assistant.status === 'active' && assistant.visibility === 'public'
            ? 'This may make the assistant unavailable through public interfaces.'
            : 'The status changes immediately after server confirmation.'}
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button
          className={deleting ? 'danger' : ''}
          disabled={pending}
          onClick={confirm}
        >
          {pending ? 'Working…' : 'Confirm'}
        </button>
        <button disabled={pending} onClick={onClose}>
          Cancel
        </button>
      </div>
    </dialog>
  );
}

export function AssistantFormPage({ mode }: { mode: 'create' | 'edit' }) {
  const auth = useAuth();
  const { api } = auth;
  const { assistantId } = useParams();
  const nav = useNavigate();
  const [detail, setDetail] = useState<AssistantDetail>();
  const [loadError, setLoadError] = useState<unknown>();
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [status, setStatus] = useState<AssistantStatus>('inactive');
  const [visibility, setVisibility] = useState<AssistantVisibility>('private');
  const [pending, setPending] = useState(false);
  const [formError, setFormError] = useState('');
  const [leavingAfterCreate, setLeavingAfterCreate] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (formError) errorRef.current?.focus();
  }, [formError]);
  const dirty = detail
    ? name !== detail.name ||
      status !== detail.status ||
      visibility !== detail.visibility
    : name !== '' || slug !== '' || status !== 'inactive' || visibility !== 'private';
  const shouldBlock = dirty && !leavingAfterCreate;
  usePrompt({
    message: 'Discard your unsaved assistant changes?',
    when: shouldBlock,
  });
  useBeforeUnload(
    (event) => {
      if (shouldBlock) event.preventDefault();
    },
    { capture: true },
  );
  useEffect(() => {
    if (leavingAfterCreate) nav('/admin/assistants');
  }, [leavingAfterCreate, nav]);
  useSessionError(loadError);
  useEffect(() => {
    if (mode === 'create' || !assistantId) return;
    const c = new AbortController();
    api
      .getAssistant(assistantId, c.signal)
      .then((x) => {
        setDetail(x);
        setName(x.name);
        setSlug(x.slug);
        setStatus(x.status);
        setVisibility(x.visibility);
      })
      .catch((e) => {
        if (e?.name !== 'AbortError') setLoadError(e);
      });
    return () => c.abort();
  }, [api, assistantId, loadAttempt, mode]);
  if (
    mode === 'edit' &&
    loadError instanceof AdminApiError &&
    loadError.kind === 'not_found'
  )
    return (
      <State
        title="Assistant not found"
        text="The requested assistant does not exist."
        link={{ label: 'Return to assistants', to: '/admin/assistants' }}
      />
    );
  if (mode === 'edit' && loadError)
    return (
      <State
        title="Unable to load assistant"
        text={message(loadError)}
        action={() => {
          setLoadError(undefined);
          setLoadAttempt((value) => value + 1);
        }}
      />
    );
  if (mode === 'edit' && !detail)
    return <p role="status">Loading assistant…</p>;
  async function submit(e: FormEvent) {
    e.preventDefault();
    setFormError('');
    if (!name.trim()) {
      setFormError('Name is required.');
      return;
    }
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
      setFormError(
        'Slug must contain lowercase letters or numbers separated by hyphens.',
      );
      return;
    }
    setPending(true);
    try {
      if (mode === 'create') {
        await api.createAssistant({
          name: name.trim(),
          slug,
          status,
          visibility,
        });
        setLeavingAfterCreate(true);
      } else if (detail) {
        const updated = await api.updateAssistant(detail.id, {
          concurrency_token: detail.concurrencyToken,
          name: name.trim(),
          status,
          visibility,
        });
        setDetail({ ...detail, ...updated });
        setFormError('Assistant saved.');
      }
    } catch (err) {
      if (err instanceof AdminApiError && err.kind === 'unauthenticated')
        return auth.sessionExpired();
      setFormError(
        err instanceof AdminApiError && err.code === 'assistant_slug_conflict'
          ? 'That slug is already in use.'
          : err instanceof AdminApiError &&
              err.code === 'assistant_update_conflict'
            ? 'This assistant was updated elsewhere. Reload before saving again.'
            : message(err),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <section className={mode === 'edit' ? 'assistant-workspace' : undefined}>
      {mode === 'edit' && detail && <AssistantNavigation assistant={detail} />}
    <form className="assistant-form" onSubmit={submit}>
      <p>
        {mode === 'create'
          ? 'Create an assistant with the backend defaults of inactive and private.'
          : 'The slug is immutable after creation.'}
      </p>
      {formError && (
        <div
          id="assistant-form-error"
          ref={errorRef}
          tabIndex={-1}
          className={formError === 'Assistant saved.' ? 'success' : 'alert'}
          role="alert"
        >
          {formError}
        </div>
      )}
      <label>
        Name
        <input
          value={name}
          maxLength={255}
          onChange={(e) => setName(e.target.value)}
          aria-invalid={formError === 'Name is required.'}
          aria-describedby={formError === 'Name is required.' ? 'assistant-form-error' : undefined}
        />
      </label>
      <label>
        Slug
        <input
          value={slug}
          maxLength={100}
          readOnly={mode === 'edit'}
          onChange={(e) => setSlug(e.target.value)}
          aria-invalid={formError.startsWith('Slug must')}
          aria-describedby={formError.startsWith('Slug must') ? 'assistant-form-error' : undefined}
        />
      </label>
      <label>
        Status
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as AssistantStatus)}
        >
          <option value="inactive">Inactive</option>
          <option value="active">Active</option>
        </select>
      </label>
      <label>
        Visibility
        <select
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as AssistantVisibility)}
        >
          <option value="private">Private — not publicly accessible</option>
          <option value="public">
            Public — may be available through public interfaces
          </option>
        </select>
      </label>
      <div className="form-actions">
        <button disabled={pending}>
          {pending ? 'Saving…' : 'Save assistant'}
        </button>
        <Link to="/admin/assistants">Cancel</Link>
        {mode === 'edit' && detail && <Link to={`/admin/assistants/${detail.id}/knowledge`}>Manage knowledge &amp; retrieval</Link>}
      </div>
    </form>
    </section>
  );
}
