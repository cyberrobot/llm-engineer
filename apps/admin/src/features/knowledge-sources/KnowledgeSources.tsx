import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
} from 'react';
import {
  Link,
  unstable_usePrompt as usePrompt,
  useBeforeUnload,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom';
import {
  AdminApiError,
  type Assistant,
  type AssistantDetail,
  type CreateKnowledgeSource,
  type KnowledgeSource,
  type KnowledgeSourceType,
} from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';

type Action = 'disable' | 'enable' | 'reingest' | 'delete';
type SelectedAction = {
  action: Action;
  source: KnowledgeSource;
  trigger: HTMLButtonElement;
};
type CreateOperation = {
  fingerprint: string;
  key: string;
};
type ReingestionOperation = {
  sourceId: string;
  key: string;
  outcome: 'unknown';
};
type ReingestionOperations = Record<string, ReingestionOperation>;

function withoutReingestionOperation(operations: ReingestionOperations, sourceId: string) {
  const remaining = { ...operations };
  delete remaining[sourceId];
  return remaining;
}

function safeMessage(error: unknown) {
  if (!(error instanceof AdminApiError)) return 'The request could not be completed.';
  if (error.kind === 'network') return 'The backend could not be reached.';
  if (error.kind === 'server') return 'The server could not complete the request.';
  if (error.kind === 'invalid_response') return 'The backend returned an invalid response.';
  if (error.kind === 'forbidden') return 'You do not have permission to perform this action.';
  return 'The request could not be completed.';
}

function isUnknownOutcome(error: unknown) {
  return error instanceof AdminApiError && ['network', 'server'].includes(error.kind);
}

function useSessionError(error: unknown) {
  const auth = useAuth();
  useEffect(() => {
    if (error instanceof AdminApiError && error.kind === 'unauthenticated') {
      auth.sessionExpired();
    }
  }, [auth, error]);
}

function State({
  title,
  text,
  retry,
  link,
}: {
  title: string;
  text: string;
  retry?: () => void;
  link?: { label: string; to: string };
}) {
  return (
    <section className="empty" role="alert">
      <h2>{title}</h2>
      <p>{text}</p>
      {retry && <button onClick={retry}>Try again</button>}
      {link && <Link to={link.to}>{link.label}</Link>}
    </section>
  );
}

function SourceBadge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value}`}>
      {value.replace('_', ' ').replace(/^./, (character) => character.toUpperCase())}
    </span>
  );
}

function loadAssistant(api: ReturnType<typeof useAuth>['api'], id: string, signal: AbortSignal) {
  return api.getAssistant(id, signal);
}

function operationNotice(state: unknown, sourceId: string | undefined) {
  if (!state || typeof state !== 'object' || !sourceId) return '';
  const value = (state as { sourceOperation?: unknown }).sourceOperation;
  if (!value || typeof value !== 'object') return '';
  const operation = value as { sourceId?: unknown; outcome?: unknown };
  if (operation.sourceId !== sourceId) return '';
  if (operation.outcome === 'reused') return 'An existing source or active ingestion job was reused.';
  if (operation.outcome === 'queued') return 'Ingestion queued.';
  return '';
}

export function KnowledgeEntryPage() {
  const { api } = useAuth();
  const [items, setItems] = useState<Assistant[]>();
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  useSessionError(error);

  useEffect(() => {
    const controller = new AbortController();
    api
      .listAssistants({ limit: 100, offset: 0 }, controller.signal)
      .then((page) => setItems(page.items))
      .catch((caught) => {
        if (caught?.name !== 'AbortError') setError(caught);
      });
    return () => controller.abort();
  }, [api, attempt]);

  if (error) {
    return (
      <State
        title="Unable to load assistants"
        text={safeMessage(error)}
        retry={() => {
          setError(undefined);
          setAttempt((value) => value + 1);
        }}
      />
    );
  }
  if (!items) return <p role="status">Loading assistants…</p>;
  return (
    <section className="feature">
      <p>Select an Assistant to manage the knowledge sources that may contribute to its answers.</p>
      {items.length === 0 ? (
        <div className="empty">
          <h2>No assistants yet</h2>
          <Link to="/admin/assistants/new">Create an assistant</Link>
        </div>
      ) : (
        <div className="source-grid">
          {items.map((item) => (
            <article className="source-card" key={item.id}>
              <h2>{item.name}</h2>
              <p><code>{item.slug}</code></p>
              <Link to={`/admin/assistants/${item.id}/knowledge`}>
                Manage knowledge for {item.name}
              </Link>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function KnowledgeSourcesPage() {
  const auth = useAuth();
  const { assistantId } = useParams();
  const [assistant, setAssistant] = useState<AssistantDetail>();
  const [page, setPage] = useState<{
    items: KnowledgeSource[];
    total: number;
    limit: number;
    offset: number;
  }>();
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<SelectedAction>();
  const [reingestionOperations, setReingestionOperations] = useState<ReingestionOperations>({});
  const [notice, setNotice] = useState('');
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const addRef = useRef<HTMLAnchorElement>(null);
  const focusAfterDelete = useRef(false);
  useSessionError(error);

  useEffect(() => {
    if (!assistantId) return;
    const controller = new AbortController();
    Promise.all([
      loadAssistant(auth.api, assistantId, controller.signal),
      auth.api.listKnowledgeSources(assistantId, { limit: 50, offset }, controller.signal),
    ])
      .then(([currentAssistant, result]) => {
        if (result.items.length === 0 && offset > 0 && offset >= result.total) {
          setOffset(result.total === 0 ? 0 : Math.floor((result.total - 1) / result.limit) * result.limit);
          return;
        }
        setAssistant(currentAssistant);
        setPage(result);
      })
      .catch((caught) => {
        if (caught?.name !== 'AbortError') setError(caught);
      });
    return () => controller.abort();
  }, [auth.api, assistantId, attempt, offset]);

  useEffect(() => {
    if (notice && document.activeElement === document.body) noticeRef.current?.focus();
  }, [notice]);

  useEffect(() => {
    if (page && focusAfterDelete.current) {
      focusAfterDelete.current = false;
      addRef.current?.focus();
    }
  }, [page]);

  if (!assistantId) return null;
  if (error instanceof AdminApiError && error.kind === 'not_found') {
    return <State title="Assistant not found" text="The requested Assistant does not exist." link={{ label: 'Return to assistants', to: '/admin/assistants' }} />;
  }
  if (error) {
    return <State title="Unable to load knowledge" text={safeMessage(error)} retry={() => { setError(undefined); setAttempt((value) => value + 1); }} />;
  }
  if (!assistant || !page) return <p role="status">Loading knowledge sources…</p>;

  function openAction(action: Action, source: KnowledgeSource, event: MouseEvent<HTMLButtonElement>) {
    setSelected({ action, source, trigger: event.currentTarget });
  }

  return (
    <section className="feature">
      <div className="page-intro">
        <div>
          <p><Link to={`/admin/assistants/${assistant.id}/edit`}>{assistant.name}</Link></p>
          <p>Enabled sources may contribute to answers after successful ingestion.</p>
        </div>
        <Link ref={addRef} className="button" to={`/admin/assistants/${assistant.id}/knowledge/new`}>
          Add knowledge source
        </Link>
      </div>
      {notice && <p ref={noticeRef} tabIndex={-1} className="success" role="status">{notice}</p>}
      {page.items.length === 0 ? (
        <div className="empty">
          <h2>No knowledge sources yet</h2>
          <p>Add direct text or a single web page for this Assistant.</p>
        </div>
      ) : (
        <div className="source-grid">
          {page.items.map((source) => (
            <article className="source-card" key={source.id}>
              <h2>{source.name}</h2>
              <Link to={`/admin/assistants/${assistant.id}/knowledge/${source.id}`}>View details for {source.name}</Link>
              <p>{source.sourceType === 'direct_text' ? 'Direct text' : `Web page · ${new URL(source.url!).hostname}`}</p>
              <div className="actions">
                <SourceBadge value={source.retrievalState} />
                {source.latestIngestion && <SourceBadge value={source.latestIngestion.status} />}
              </div>
              {source.latestIngestion?.currentStep && <p>Current step: {source.latestIngestion.currentStep}</p>}
              <div className="actions source-actions">
                <button className="link-button" onClick={(event) => openAction(source.retrievalState === 'enabled' ? 'disable' : 'enable', source, event)} aria-label={`${source.retrievalState === 'enabled' ? 'Disable' : 'Enable'} ${source.name}`}>
                  {source.retrievalState === 'enabled' ? 'Disable' : 'Enable'}
                </button>
                <button className="link-button" onClick={(event) => openAction('reingest', source, event)} aria-label={`Re-ingest ${source.name}`}>Re-ingest</button>
                <button className="danger-link" onClick={(event) => openAction('delete', source, event)} aria-label={`Delete ${source.name}`}>Delete</button>
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="pagination">
        <p>{page.total ? `Showing ${page.offset + 1}–${page.offset + page.items.length} of ${page.total}` : '0 sources'}</p>
        <div className="actions">
          <button className="secondary-action" onClick={() => { setPage(undefined); setAttempt((value) => value + 1); }}>Refresh</button>
          <button disabled={offset === 0} onClick={() => { setPage(undefined); setOffset(Math.max(0, offset - page.limit)); }}>Previous</button>
          <button disabled={offset + page.items.length >= page.total} onClick={() => { setPage(undefined); setOffset(offset + page.limit); }}>Next</button>
        </div>
      </div>
      {selected && (
        <SourceActionDialog
          {...selected}
          assistantId={assistantId}
          reingestionOperation={reingestionOperations[selected.source.id]}
          onReingestionOperationChange={(operation) => setReingestionOperations((current) => {
            if (operation) return { ...current, [selected.source.id]: operation };
            return withoutReingestionOperation(current, selected.source.id);
          })}
          onClose={() => setSelected(undefined)}
          onAuthoritativeRefresh={async (signal) => {
            const updated = await auth.api.getKnowledgeSource(assistantId, selected.source.id, signal);
            setPage((current) => current && ({ ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) }));
            setReingestionOperations((current) => withoutReingestionOperation(current, selected.source.id));
            setSelected(undefined);
            setNotice('Authoritative source state refreshed.');
          }}
          onUpdated={(updated, message) => {
            setPage((current) => current && ({ ...current, items: current.items.map((item) => item.id === updated.id ? updated : item) }));
            setSelected(undefined);
            setNotice(message);
          }}
          onDeleted={() => {
            setSelected(undefined);
            setNotice('Knowledge source deleted.');
            setPage(undefined);
            setAttempt((value) => value + 1);
            focusAfterDelete.current = true;
          }}
        />
      )}
    </section>
  );
}

export function KnowledgeSourceCreatePage() {
  const auth = useAuth();
  const { assistantId } = useParams();
  const navigate = useNavigate();
  const [assistant, setAssistant] = useState<AssistantDetail>();
  const [loadError, setLoadError] = useState<unknown>();
  const [type, setType] = useState<KnowledgeSourceType>('direct_text');
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [url, setUrl] = useState('');
  const [pending, setPending] = useState(false);
  const [leaving, setLeaving] = useState<{
    to: string;
    state: { sourceOperation: { sourceId: string; outcome: 'queued' | 'reused' } };
  }>();
  const [formError, setFormError] = useState('');
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconciliationNotice, setReconciliationNotice] = useState('');
  const [operation, setOperation] = useState<CreateOperation>();
  const reconciliationController = useRef<AbortController | undefined>(undefined);
  const errorRef = useRef<HTMLDivElement>(null);
  const dirty = Boolean(name || content || url);
  usePrompt({ when: dirty && !leaving, message: 'Discard your unsaved knowledge source?' });
  useBeforeUnload((event) => { if (dirty && !leaving) event.preventDefault(); }, { capture: true });
  useSessionError(loadError);

  useEffect(() => { if (formError) errorRef.current?.focus(); }, [formError]);
  useEffect(() => {
    if (leaving) navigate(leaving.to, { state: leaving.state });
  }, [leaving, navigate]);
  useEffect(() => {
    if (!assistantId) return;
    const controller = new AbortController();
    loadAssistant(auth.api, assistantId, controller.signal)
      .then(setAssistant)
      .catch((caught) => { if (caught?.name !== 'AbortError') setLoadError(caught); });
    return () => controller.abort();
  }, [assistantId, auth.api]);
  useEffect(() => () => reconciliationController.current?.abort(), []);

  if (loadError instanceof AdminApiError && loadError.kind === 'not_found') {
    return <State title="Assistant not found" text="The requested Assistant does not exist." link={{ label: 'Return to assistants', to: '/admin/assistants' }} />;
  }
  if (loadError) return <State title="Unable to load assistant" text={safeMessage(loadError)} />;
  if (!assistant || !assistantId) return <p role="status">Loading assistant…</p>;
  const confirmedAssistantId = assistantId;

  function input(): CreateKnowledgeSource | null {
    if (!name.trim()) { setFormError('Name is required.'); return null; }
    if (type === 'direct_text' && !content.trim()) { setFormError('Content is required.'); return null; }
    if (type === 'url') {
      try {
        const parsed = new URL(url);
        if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash) throw new Error();
      } catch {
        setFormError('Enter an absolute HTTP or HTTPS URL without credentials or a fragment.');
        return null;
      }
    }
    return type === 'direct_text'
      ? { source_type: 'direct_text', name: name.trim(), direct_text: content }
      : { source_type: 'url', name: name.trim(), url };
  }

  async function execute(request: CreateKnowledgeSource) {
    setFormError('');
    setReconciliationNotice('');
    const fingerprint = JSON.stringify(request);
    if (unknownOutcome && operation?.fingerprint !== fingerprint) {
      setFormError('Authoritative state must be refreshed before starting a changed creation operation.');
      return;
    }
    const submittedOperation = operation?.fingerprint === fingerprint
      ? operation
      : { fingerprint, key: crypto.randomUUID() };
    setOperation(submittedOperation);
    setPending(true);
    try {
      const created = await auth.api.createKnowledgeSource(confirmedAssistantId, request, submittedOperation.key);
      setOperation(undefined);
      setLeaving({
        to: `/admin/assistants/${confirmedAssistantId}/knowledge/${created.id}`,
        state: { sourceOperation: { sourceId: created.id, outcome: created.activeJobReused ? 'reused' : 'queued' } },
      });
    } catch (caught) {
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') return auth.sessionExpired();
      if (isUnknownOutcome(caught)) {
        setUnknownOutcome(true);
        setFormError('The request outcome is unknown. Retry the identical request with the same operation key, or refresh authoritative state before changing it.');
      } else {
        setOperation(undefined);
        setFormError(caught instanceof AdminApiError && caught.code === 'idempotency_key_conflict'
          ? 'This operation conflicts with an earlier request. Refresh before trying again.'
          : safeMessage(caught));
      }
    } finally {
      setPending(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError('');
    const request = input();
    if (request) await execute(request);
  }

  function changed(update: () => void) {
    update();
    setFormError('');
    setReconciliationNotice('');
  }

  function currentFingerprint() {
    const request = type === 'direct_text'
      ? { source_type: 'direct_text' as const, name: name.trim(), direct_text: content }
      : { source_type: 'url' as const, name: name.trim(), url };
    return JSON.stringify(request);
  }

  async function reconcileAuthoritativeState() {
    reconciliationController.current?.abort();
    const controller = new AbortController();
    reconciliationController.current = controller;
    setReconciling(true);
    setFormError('');
    setReconciliationNotice('');
    try {
      await auth.api.listKnowledgeSources(confirmedAssistantId, { limit: 50, offset: 0 }, controller.signal);
      if (reconciliationController.current !== controller) return;
      setOperation(undefined);
      setUnknownOutcome(false);
      setReconciliationNotice('Authoritative source state was refreshed. You may now start a new creation operation.');
    } catch (caught) {
      if (caught instanceof Error && caught.name === 'AbortError') return;
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') return auth.sessionExpired();
      if (reconciliationController.current !== controller) return;
      setFormError(`Authoritative state could not be refreshed. ${safeMessage(caught)}`);
    } finally {
      if (reconciliationController.current === controller) {
        reconciliationController.current = undefined;
        setReconciling(false);
      }
    }
  }

  const unresolvedPayloadChanged = unknownOutcome
    && operation?.fingerprint !== currentFingerprint();
  const nameInvalid = formError === 'Name is required.';
  const contentInvalid = formError === 'Content is required.';
  const urlInvalid = formError.startsWith('Enter an absolute');
  return (
    <form className="assistant-form" onSubmit={submit}>
      <p>Add knowledge to <strong>{assistant.name}</strong>. URL sources retrieve one page only. Switching source type preserves but never submits the hidden field.</p>
      {reconciliationNotice && <p className="success" role="status">{reconciliationNotice}</p>}
      {formError && <div id="source-form-error" ref={errorRef} tabIndex={-1} className="alert" role="alert">{formError}</div>}
      {unresolvedPayloadChanged && <p className="alert" role="status">The pending unknown operation cannot be retried with the modified payload. Refresh authoritative state before starting a changed creation operation.</p>}
      <fieldset>
        <legend>Source type</legend>
        <label><input type="radio" name="source-type" checked={type === 'direct_text'} onChange={() => changed(() => setType('direct_text'))} /> Direct text</label>
        <label><input type="radio" name="source-type" checked={type === 'url'} onChange={() => changed(() => setType('url'))} /> Web page URL</label>
      </fieldset>
      <label>Name<input value={name} maxLength={255} onChange={(event) => changed(() => setName(event.target.value))} aria-invalid={nameInvalid} aria-describedby={nameInvalid ? 'source-form-error' : undefined} /></label>
      {type === 'direct_text' ? (
        <label>Content<textarea value={content} maxLength={100000} rows={12} onChange={(event) => changed(() => setContent(event.target.value))} aria-invalid={contentInvalid} aria-describedby={contentInvalid ? 'source-form-error' : undefined} /></label>
      ) : (
        <label>URL<input type="url" value={url} onChange={(event) => changed(() => setUrl(event.target.value))} aria-invalid={urlInvalid} aria-describedby={urlInvalid ? 'source-form-error' : undefined} /></label>
      )}
      <div className="form-actions">
        <button disabled={pending || reconciling || unresolvedPayloadChanged}>{pending ? 'Adding…' : 'Add knowledge source'}</button>
        {unknownOutcome && !unresolvedPayloadChanged && <button type="button" disabled={pending || reconciling} onClick={() => { const request = input(); if (request) void execute(request); }}>Retry identical request</button>}
        {unknownOutcome && <button type="button" disabled={pending || reconciling} onClick={() => void reconcileAuthoritativeState()}>{reconciling ? 'Refreshing authoritative state…' : 'Refresh authoritative state'}</button>}
        <Link to={`/admin/assistants/${confirmedAssistantId}/knowledge`}>Cancel</Link>
      </div>
    </form>
  );
}

export function KnowledgeSourceDetailPage() {
  const auth = useAuth();
  const { assistantId, sourceId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [assistant, setAssistant] = useState<AssistantDetail>();
  const [source, setSource] = useState<KnowledgeSource>();
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState(() => operationNotice(location.state, sourceId));
  const [selected, setSelected] = useState<SelectedAction>();
  const [reingestionOperations, setReingestionOperations] = useState<ReingestionOperations>({});
  const noticeRef = useRef<HTMLParagraphElement>(null);
  const focusCreationNotice = useRef(Boolean(operationNotice(location.state, sourceId)));
  useSessionError(error);

  useEffect(() => {
    if (!assistantId || !sourceId) return;
    const controller = new AbortController();
    Promise.all([
      auth.api.getAssistant(assistantId, controller.signal),
      auth.api.getKnowledgeSource(assistantId, sourceId, controller.signal),
    ])
      .then(([currentAssistant, item]) => { setAssistant(currentAssistant); setSource(item); })
      .catch((caught) => { if (caught?.name !== 'AbortError') setError(caught); });
    return () => controller.abort();
  }, [assistantId, sourceId, auth.api, attempt]);

  useEffect(() => {
    if (assistant && source && notice && focusCreationNotice.current) {
      focusCreationNotice.current = false;
      noticeRef.current?.focus();
    }
  }, [assistant, notice, source]);

  useEffect(() => {
    if (operationNotice(location.state, sourceId)) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate, sourceId]);

  if (!assistantId || !sourceId) return null;
  if (error instanceof AdminApiError && error.kind === 'not_found') {
    return <State title="Knowledge source not found" text="The requested source does not exist for this Assistant." link={{ label: 'Return to knowledge sources', to: `/admin/assistants/${assistantId}/knowledge` }} />;
  }
  if (error) return <State title="Unable to load knowledge source" text={safeMessage(error)} retry={() => { setError(undefined); setAttempt((value) => value + 1); }} />;
  if (!source || !assistant) return <p role="status">Loading knowledge source…</p>;
  const ingestion = source.latestIngestion;

  function openAction(action: Action, event: MouseEvent<HTMLButtonElement>) {
    setSelected({ action, source: source!, trigger: event.currentTarget });
  }

  return (
    <section className="source-detail">
      <p>Knowledge for <strong>{assistant.name}</strong> · <Link to={`/admin/assistants/${assistantId}/knowledge`}>Return to knowledge sources</Link></p>
      {notice && <p ref={noticeRef} tabIndex={-1} className="success" role="status">{notice}</p>}
      <div className="source-card">
        <h2>{source.name}</h2>
        <dl>
          <dt>Type</dt><dd>{source.sourceType === 'direct_text' ? 'Direct text' : 'Web page URL'}</dd>
          <dt>Retrieval</dt><dd><SourceBadge value={source.retrievalState} /></dd>
          <dt>Created</dt><dd>{new Date(source.createdAt).toLocaleString()}</dd>
          <dt>Updated</dt><dd>{new Date(source.updatedAt).toLocaleString()}</dd>
        </dl>
        {source.url && <p className="break-content"><a href={source.url} target="_blank" rel="noreferrer">{source.url}</a></p>}
        {source.directText !== null && <pre className="source-content">{source.directText}</pre>}
      </div>
      <section className="source-card">
        <h2>Latest ingestion</h2>
        {ingestion ? (
          <>
            <dl>
              <dt>Status</dt><dd><SourceBadge value={ingestion.status} /></dd>
              {ingestion.currentStep && <><dt>Current step</dt><dd>{ingestion.currentStep}</dd></>}
              <dt>Job created</dt><dd>{new Date(ingestion.createdAt).toLocaleString()}</dd>
              {ingestion.startedAt && <><dt>Started</dt><dd>{new Date(ingestion.startedAt).toLocaleString()}</dd></>}
              {ingestion.completedAt && <><dt>Completed</dt><dd>{new Date(ingestion.completedAt).toLocaleString()}</dd></>}
              {ingestion.failureCode && <><dt>Failure code</dt><dd><code>{ingestion.failureCode}</code></dd></>}
            </dl>
            {ingestion.failureMessage && <p className="alert">{ingestion.failureMessage}</p>}
            {ingestion.status === 'failed' && <p>After the underlying source is available, re-ingestion may be attempted. The previous committed knowledge remains available unless retrieval is disabled.</p>}
          </>
        ) : <p>No ingestion job was reported.</p>}
      </section>
      <div className="actions">
        <button onClick={(event) => openAction(source.retrievalState === 'enabled' ? 'disable' : 'enable', event)} aria-label={`${source.retrievalState === 'enabled' ? 'Disable' : 'Enable'} ${source.name}`}>{source.retrievalState === 'enabled' ? 'Disable retrieval' : 'Enable retrieval'}</button>
        <button onClick={(event) => openAction('reingest', event)} aria-label={`Re-ingest ${source.name}`}>Re-ingest</button>
        <button className="danger" onClick={(event) => openAction('delete', event)} aria-label={`Delete ${source.name}`}>Delete</button>
        <button className="secondary-action" onClick={() => setAttempt((value) => value + 1)}>Refresh</button>
      </div>
      {selected && (
        <SourceActionDialog
          {...selected}
          assistantId={assistantId}
          reingestionOperation={reingestionOperations[source.id]}
          onReingestionOperationChange={(operation) => setReingestionOperations(operation ? { [source.id]: operation } : {})}
          onClose={() => setSelected(undefined)}
          onAuthoritativeRefresh={async (signal) => {
            const updated = await auth.api.getKnowledgeSource(assistantId, source.id, signal);
            setSource(updated);
            setReingestionOperations({});
            setSelected(undefined);
            setNotice('Authoritative source state refreshed.');
          }}
          onUpdated={(updated, message) => { setSource(updated); setSelected(undefined); setNotice(message); }}
          onDeleted={() => navigate(`/admin/assistants/${assistantId}/knowledge`, { state: { deletedSource: source.id } })}
        />
      )}
    </section>
  );
}

function SourceActionDialog({
  action,
  source,
  trigger,
  assistantId,
  reingestionOperation,
  onReingestionOperationChange,
  onClose,
  onAuthoritativeRefresh,
  onUpdated,
  onDeleted,
}: SelectedAction & {
  assistantId: string;
  reingestionOperation?: ReingestionOperation;
  onReingestionOperationChange: (operation: ReingestionOperation | undefined) => void;
  onClose: () => void;
  onAuthoritativeRefresh: (signal: AbortSignal) => Promise<void>;
  onUpdated: (source: KnowledgeSource, message: string) => void;
  onDeleted: () => void;
}) {
  const auth = useAuth();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const refreshController = useRef<AbortController | undefined>(undefined);
  const unresolvedOperation = action === 'reingest' && reingestionOperation?.sourceId === source.id
    ? reingestionOperation
    : undefined;
  useEffect(() => dialogRef.current?.showModal(), []);
  useEffect(() => () => refreshController.current?.abort(), []);
  const label = action === 'reingest' ? 're-ingestion' : action === 'delete' ? 'deletion' : action;

  function close(callback: () => void, restore = true) {
    if (dialogRef.current?.open) dialogRef.current.close();
    callback();
    if (restore) queueMicrotask(() => trigger.focus());
  }

  async function confirm() {
    setPending(true);
    setError('');
    let submittedReingestionKey: string | undefined;
    try {
      if (action === 'delete') {
        await auth.api.deleteKnowledgeSource(assistantId, source.id);
        close(onDeleted, false);
        return;
      }
      if (action === 'reingest') {
        const key = unresolvedOperation?.key ?? crypto.randomUUID();
        submittedReingestionKey = key;
        const updated = await auth.api.reingestKnowledgeSource(assistantId, source.id, key);
        onReingestionOperationChange(undefined);
        close(() => onUpdated(updated, updated.activeJobReused ? 'The active ingestion job was reused.' : 'Re-ingestion queued.'));
        return;
      }
      const state = action === 'disable' ? 'disabled' : 'enabled';
      const updated = await auth.api.updateKnowledgeSourceRetrieval(assistantId, source.id, state);
      close(() => onUpdated(updated, `Retrieval ${state}.`));
    } catch (caught) {
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') return auth.sessionExpired();
      if (action === 'delete' && caught instanceof AdminApiError && caught.kind === 'not_found') {
        close(onDeleted, false);
        return;
      }
      if (action === 'reingest' && isUnknownOutcome(caught)) {
        if (submittedReingestionKey) {
          onReingestionOperationChange({ sourceId: source.id, key: submittedReingestionKey, outcome: 'unknown' });
        }
        setError('The re-ingestion outcome is unknown. Retry the identical operation with the same key, or refresh authoritative state.');
      } else {
        if (action === 'reingest') onReingestionOperationChange(undefined);
        setError(caught instanceof AdminApiError && caught.code === 'active_ingestion'
          ? 'This source cannot be deleted while ingestion is active.'
          : caught instanceof AdminApiError && caught.code === 'idempotency_key_conflict'
            ? 'This operation conflicts with an earlier request. Refresh authoritative state before retrying.'
            : safeMessage(caught));
      }
      setPending(false);
    }
  }

  async function refreshAuthoritativeState() {
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    setPending(true);
    setError('');
    try {
      await onAuthoritativeRefresh(controller.signal);
      if (refreshController.current !== controller) return;
      close(() => undefined);
    } catch (caught) {
      if (caught instanceof Error && caught.name === 'AbortError') return;
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') return auth.sessionExpired();
      if (refreshController.current !== controller) return;
      setError(`Authoritative state could not be refreshed. ${safeMessage(caught)}`);
      setPending(false);
    } finally {
      if (refreshController.current === controller) refreshController.current = undefined;
    }
  }

  return (
    <dialog ref={dialogRef} onCancel={(event) => { event.preventDefault(); close(onClose); }} aria-labelledby="source-dialog-title">
      <h2 id="source-dialog-title">Confirm {label}</h2>
      <p>{action === 'disable'
        ? 'Stored knowledge remains present but will be excluded from retrieval.'
        : action === 'delete'
          ? `Delete ${source.name} and its owned indexed representation? Deletion is blocked while ingestion is queued or running.`
          : action === 'reingest'
            ? unresolvedOperation
              ? 'The previous re-ingestion outcome is still unknown. Retry the identical operation or refresh authoritative source state.'
              : 'Reprocess the persisted source without creating a duplicate.'
            : 'The currently committed knowledge may participate in retrieval.'}</p>
      {pending && <p role="status">Operation in progress…</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      <div className="dialog-actions">
        <button className={action === 'delete' ? 'danger' : ''} disabled={pending} onClick={confirm}>
          {pending ? 'Working…' : unresolvedOperation ? 'Retry identical re-ingestion' : `Confirm ${label}`}
        </button>
        {unresolvedOperation && <button disabled={pending} onClick={() => void refreshAuthoritativeState()}>Refresh authoritative state</button>}
        <button disabled={pending} onClick={() => close(onClose)}>Cancel</button>
      </div>
    </dialog>
  );
}
