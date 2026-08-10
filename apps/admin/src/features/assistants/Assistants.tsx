import { useEffect, useRef, useState, type FormEvent } from 'react';
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
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<AssistantStatus | ''>('');
  const [visibilityFilter, setVisibilityFilter] = useState<AssistantVisibility | ''>('');
  const [action, setAction] = useState<Assistant>();
  const [notice, setNotice] = useState('');
  const noticeRef = useRef<HTMLParagraphElement>(null);
  useSessionError(error);
  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);
  useEffect(() => {
    const controller = new AbortController();
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
        setPage(result);
      })
      .catch((e) => {
        if (e?.name !== 'AbortError') setError(e);
      });
    return () => controller.abort();
  }, [api, attempt, offset, statusFilter, visibilityFilter]);
  if (error)
    return (
      <State
        title="Unable to load assistants"
        text={message(error)}
        action={() => {
          setError(undefined);
          setPage(null);
          setAttempt((x) => x + 1);
        }}
      />
    );
  if (!page) return <p role="status">Loading assistants…</p>;
  return (
    <section className="feature">
      <div className="page-intro">
        <p>
          Manage each assistant’s identity, operational status, and public
          visibility.
        </p>
        <Link className="button" to="/admin/assistants/new">
          Create assistant
        </Link>
      </div>
      <div className="filters" aria-label="Filter assistants">
        <label>
          Status
          <select
            value={statusFilter}
            onChange={(event) => {
              setPage(null);
              setOffset(0);
              setStatusFilter(event.target.value as AssistantStatus | '');
            }}
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
            onChange={(event) => {
              setPage(null);
              setOffset(0);
              setVisibilityFilter(event.target.value as AssistantVisibility | '');
            }}
          >
            <option value="">All visibilities</option>
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
        </label>
      </div>
      {notice && (
        <p ref={noticeRef} tabIndex={-1} className="success" role="status">
          {notice}
        </p>
      )}
      {page.items.length === 0 && page.total === 0 ? (
        <div className="empty">
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
            </>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Status</th>
                <th>Visibility</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>
                    <code>{a.slug}</code>
                  </td>
                  <td>
                    <Badge value={a.status} />
                  </td>
                  <td>
                    <Badge value={a.visibility} />
                  </td>
                  <td>{new Date(a.updatedAt).toLocaleDateString()}</td>
                  <td className="actions">
                    <Link to={`/admin/assistants/${a.id}/edit`}>Edit</Link>
                    <button
                      className="link-button"
                      aria-label={`${a.status === 'active' ? 'Deactivate' : 'Activate'} ${a.name}`}
                      onClick={() => setAction(a)}
                    >
                      {a.status === 'active' ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      className="danger-link"
                      aria-label={`Delete ${a.name}`}
                      onClick={() =>
                        setAction({ ...a, name: `DELETE:${a.name}` })
                      }
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
      )}{' '}
      {action && (
        <ActionDialog
          assistant={action}
          onClose={() => setAction(undefined)}
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
  onClose,
  onDone,
}: {
  assistant: Assistant;
  onClose: () => void;
  onDone: (deleted: boolean) => void;
}) {
  const auth = useAuth();
  const ref = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const deleting = assistant.name.startsWith('DELETE:');
  const name = deleting ? assistant.name.slice(7) : assistant.name;
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
  );
}
