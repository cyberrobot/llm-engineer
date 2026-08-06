import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, unstable_usePrompt as usePrompt, useBeforeUnload, useNavigate, useParams } from 'react-router-dom';
import { AdminApiError, type Assistant, type AssistantDetail, type KnowledgeSource, type KnowledgeSourceType } from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';

function safeMessage(error: unknown) {
  if (!(error instanceof AdminApiError)) return 'The request could not be completed.';
  if (error.kind === 'network') return 'The backend could not be reached. Try again.';
  if (error.kind === 'server') return 'The server could not complete the request. Try again.';
  if (error.kind === 'invalid_response') return 'The backend returned an invalid response.';
  if (error.kind === 'forbidden') return 'You do not have permission to perform this action.';
  return 'The request could not be completed.';
}

function useSessionError(error: unknown) {
  const auth = useAuth();
  useEffect(() => {
    if (error instanceof AdminApiError && error.kind === 'unauthenticated') auth.sessionExpired();
  }, [auth, error]);
}

function State({ title, text, retry, link }: { title: string; text: string; retry?: () => void; link?: { label: string; to: string } }) {
  return <section className="empty" role="alert"><h2>{title}</h2><p>{text}</p>{retry && <button onClick={retry}>Try again</button>}{link && <Link to={link.to}>{link.label}</Link>}</section>;
}

function SourceBadge({ value }: { value: string }) {
  return <span className={`badge badge-${value}`}>{value.replace('_', ' ').replace(/^./, x => x.toUpperCase())}</span>;
}

function loadAssistant(api: ReturnType<typeof useAuth>['api'], id: string, signal: AbortSignal) {
  return api.getAssistant(id, signal);
}

export function KnowledgeEntryPage() {
  const { api } = useAuth();
  const [items, setItems] = useState<Assistant[]>();
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  useSessionError(error);
  useEffect(() => {
    const controller = new AbortController();
    api.listAssistants({ limit: 100, offset: 0 }, controller.signal).then(page => setItems(page.items)).catch(e => { if (e?.name !== 'AbortError') setError(e); });
    return () => controller.abort();
  }, [api, attempt]);
  if (error) return <State title="Unable to load assistants" text={safeMessage(error)} retry={() => { setError(undefined); setAttempt(x => x + 1); }} />;
  if (!items) return <p role="status">Loading assistants…</p>;
  return <section className="feature"><p>Select an Assistant to manage the knowledge sources that may contribute to its answers.</p>{items.length === 0 ? <div className="empty"><h2>No assistants yet</h2><Link to="/admin/assistants/new">Create an assistant</Link></div> : <div className="source-grid">{items.map(item => <article className="source-card" key={item.id}><h2>{item.name}</h2><p><code>{item.slug}</code></p><Link to={`/admin/assistants/${item.id}/knowledge`}>Manage knowledge for {item.name}</Link></article>)}</div>}</section>;
}

export function KnowledgeSourcesPage() {
  const auth = useAuth();
  const { assistantId } = useParams();
  const [assistant, setAssistant] = useState<AssistantDetail>();
  const [page, setPage] = useState<{ items: KnowledgeSource[]; total: number; limit: number; offset: number }>();
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  useSessionError(error);
  useEffect(() => {
    if (!assistantId) return;
    const controller = new AbortController();
    Promise.all([loadAssistant(auth.api, assistantId, controller.signal), auth.api.listKnowledgeSources(assistantId, { limit: 50, offset }, controller.signal)])
      .then(([a, result]) => {
        if (result.items.length === 0 && offset > 0 && offset >= result.total) { setOffset(Math.max(0, Math.floor((result.total - 1) / result.limit) * result.limit)); return; }
        setAssistant(a); setPage(result);
      }).catch(e => { if (e?.name !== 'AbortError') setError(e); });
    return () => controller.abort();
  }, [auth.api, assistantId, attempt, offset]);
  if (!assistantId) return null;
  if (error instanceof AdminApiError && error.kind === 'not_found') return <State title="Assistant not found" text="The requested Assistant or source does not exist." link={{ label: 'Return to assistants', to: '/admin/assistants' }} />;
  if (error) return <State title="Unable to load knowledge" text={safeMessage(error)} retry={() => { setError(undefined); setAttempt(x => x + 1); }} />;
  if (!assistant || !page) return <p role="status">Loading knowledge sources…</p>;
  return <section className="feature">
    <div className="page-intro"><div><p><Link to={`/admin/assistants/${assistant.id}/edit`}>{assistant.name}</Link></p><p>Enabled sources may contribute to answers after successful ingestion.</p></div><Link className="button" to={`/admin/assistants/${assistant.id}/knowledge/new`}>Add knowledge source</Link></div>
    {page.items.length === 0 ? <div className="empty"><h2>No knowledge sources yet</h2><p>Add direct text or a single web page for this Assistant.</p></div> : <div className="source-grid">{page.items.map(source => <article className="source-card" key={source.id}><h2><Link to={`/admin/assistants/${assistant.id}/knowledge/${source.id}`}>{source.name}</Link></h2><p>{source.sourceType === 'direct_text' ? 'Direct text' : `Web page · ${new URL(source.url!).hostname}`}</p><div className="actions"><SourceBadge value={source.retrievalState}/>{source.latestIngestion && <SourceBadge value={source.latestIngestion.status}/>}</div>{source.latestIngestion?.currentStep && <p>Current step: {source.latestIngestion.currentStep}</p>}</article>)}</div>}
    <div className="pagination"><p>{page.total ? `Showing ${page.offset + 1}–${page.offset + page.items.length} of ${page.total}` : '0 sources'}</p><div className="actions"><button className="secondary-action" onClick={() => { setPage(undefined); setAttempt(x => x + 1); }}>Refresh</button><button disabled={offset === 0} onClick={() => { setPage(undefined); setOffset(Math.max(0, offset - 50)); }}>Previous</button><button disabled={offset + page.items.length >= page.total} onClick={() => { setPage(undefined); setOffset(offset + 50); }}>Next</button></div></div>
  </section>;
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
  const [leaving, setLeaving] = useState('');
  const [formError, setFormError] = useState('');
  const errorRef = useRef<HTMLDivElement>(null);
  const dirty = Boolean(name || content || url);
  usePrompt({ when: dirty && !leaving, message: 'Discard your unsaved knowledge source?' });
  useBeforeUnload(e => { if (dirty && !leaving) e.preventDefault(); }, { capture: true });
  useSessionError(loadError);
  useEffect(() => { if (formError) errorRef.current?.focus(); }, [formError]);
  useEffect(() => { if (leaving) navigate(leaving); }, [leaving, navigate]);
  useEffect(() => { if (!assistantId) return; const c = new AbortController(); loadAssistant(auth.api, assistantId, c.signal).then(setAssistant).catch(e => { if (e?.name !== 'AbortError') setLoadError(e); }); return () => c.abort(); }, [assistantId, auth.api]);
  if (loadError instanceof AdminApiError && loadError.kind === 'not_found') return <State title="Assistant not found" text="The requested Assistant does not exist." link={{ label: 'Return to assistants', to: '/admin/assistants' }} />;
  if (loadError) return <State title="Unable to load assistant" text={safeMessage(loadError)} />;
  if (!assistant || !assistantId) return <p role="status">Loading assistant…</p>;
  const confirmedAssistantId = assistantId;
  async function submit(event: FormEvent) {
    event.preventDefault(); setFormError('');
    if (!name.trim()) return setFormError('Name is required.');
    if (type === 'direct_text' && !content.trim()) return setFormError('Content is required.');
    if (type === 'url') { try { const parsed = new URL(url); if (!['http:','https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.hash) throw new Error(); } catch { return setFormError('Enter an absolute HTTP or HTTPS URL without credentials or a fragment.'); } }
    setPending(true);
    try {
      const created = await auth.api.createKnowledgeSource(confirmedAssistantId, type === 'direct_text' ? { source_type:'direct_text', name:name.trim(), direct_text:content } : { source_type:'url', name:name.trim(), url });
      setLeaving(`/admin/assistants/${confirmedAssistantId}/knowledge/${created.id}`);
    } catch (e) {
      if (e instanceof AdminApiError && e.kind === 'unauthenticated') return auth.sessionExpired();
      setFormError(e instanceof AdminApiError && e.code === 'idempotency_key_conflict' ? 'This operation conflicts with an earlier request. Refresh before trying again.' : safeMessage(e));
    } finally { setPending(false); }
  }
  const nameInvalid = formError === 'Name is required.';
  const contentInvalid = formError === 'Content is required.';
  const urlInvalid = formError.startsWith('Enter an absolute');
  return <form className="assistant-form" onSubmit={submit}><p>Add knowledge to <strong>{assistant.name}</strong>. URL sources retrieve one page only. Switching source type preserves but never submits the hidden field.</p>{formError && <div id="source-form-error" ref={errorRef} tabIndex={-1} className="alert" role="alert">{formError}</div>}<fieldset><legend>Source type</legend><label><input type="radio" name="source-type" checked={type === 'direct_text'} onChange={() => setType('direct_text')} /> Direct text</label><label><input type="radio" name="source-type" checked={type === 'url'} onChange={() => setType('url')} /> Web page URL</label></fieldset><label>Name<input value={name} maxLength={255} onChange={e => setName(e.target.value)} aria-invalid={nameInvalid} aria-describedby={nameInvalid ? 'source-form-error' : undefined} /></label>{type === 'direct_text' ? <label>Content<textarea value={content} maxLength={100000} rows={12} onChange={e => setContent(e.target.value)} aria-invalid={contentInvalid} aria-describedby={contentInvalid ? 'source-form-error' : undefined} /></label> : <label>URL<input type="url" value={url} onChange={e => setUrl(e.target.value)} aria-invalid={urlInvalid} aria-describedby={urlInvalid ? 'source-form-error' : undefined} /></label>}<div className="form-actions"><button disabled={pending}>{pending ? 'Adding…' : 'Add knowledge source'}</button><Link to={`/admin/assistants/${confirmedAssistantId}/knowledge`}>Cancel</Link></div></form>;
}

type Action = 'disable' | 'enable' | 'reingest' | 'delete';
export function KnowledgeSourceDetailPage() {
  const auth = useAuth();
  const { assistantId, sourceId } = useParams();
  const navigate = useNavigate();
  const [assistant, setAssistant] = useState<AssistantDetail>();
  const [source, setSource] = useState<KnowledgeSource>();
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState('');
  const [action, setAction] = useState<Action>();
  useSessionError(error);
  useEffect(() => { if (!assistantId || !sourceId) return; const c = new AbortController(); Promise.all([auth.api.getAssistant(assistantId, c.signal), auth.api.getKnowledgeSource(assistantId, sourceId, c.signal)]).then(([a, item]) => { setAssistant(a); setSource(item); }).catch(e => { if (e?.name !== 'AbortError') setError(e); }); return () => c.abort(); }, [assistantId, sourceId, auth.api, attempt]);
  if (!assistantId || !sourceId) return null;
  if (error instanceof AdminApiError && error.kind === 'not_found') return <State title="Knowledge source not found" text="The requested source does not exist for this Assistant." link={{ label:'Return to knowledge sources',to:`/admin/assistants/${assistantId}/knowledge` }} />;
  if (error) return <State title="Unable to load knowledge source" text={safeMessage(error)} retry={() => { setError(undefined); setAttempt(x => x + 1); }} />;
  if (!source || !assistant) return <p role="status">Loading knowledge source…</p>;
  const ingestion = source.latestIngestion;
  return <section className="source-detail"><p>Knowledge for <strong>{assistant.name}</strong> · <Link to={`/admin/assistants/${assistantId}/knowledge`}>Return to knowledge sources</Link></p>{notice && <p className="success" role="status">{notice}</p>}<div className="source-card"><h2>{source.name}</h2><dl><dt>Type</dt><dd>{source.sourceType === 'direct_text' ? 'Direct text' : 'Web page URL'}</dd><dt>Retrieval</dt><dd><SourceBadge value={source.retrievalState}/></dd><dt>Updated</dt><dd>{new Date(source.updatedAt).toLocaleString()}</dd></dl>{source.url && <p className="break-content"><a href={source.url} target="_blank" rel="noreferrer">{source.url}</a></p>}{source.directText !== null && <pre className="source-content">{source.directText}</pre>}</div><section className="source-card"><h2>Latest ingestion</h2>{ingestion ? <><p><SourceBadge value={ingestion.status}/>{ingestion.currentStep && ` Current step: ${ingestion.currentStep}`}</p>{ingestion.failureMessage && <p className="alert">{ingestion.failureMessage}</p>}</> : <p>No ingestion job was reported.</p>}</section><div className="actions"><button onClick={() => setAction(source.retrievalState === 'enabled' ? 'disable' : 'enable')} aria-label={`${source.retrievalState === 'enabled' ? 'Disable' : 'Enable'} ${source.name}`}>{source.retrievalState === 'enabled' ? 'Disable retrieval' : 'Enable retrieval'}</button><button onClick={() => setAction('reingest')} aria-label={`Re-ingest ${source.name}`}>Re-ingest</button><button className="danger" onClick={() => setAction('delete')} aria-label={`Delete ${source.name}`}>Delete</button><button className="secondary-action" onClick={() => setAttempt(x => x + 1)}>Refresh</button></div>{action && <SourceActionDialog action={action} source={source} assistantId={assistantId} onClose={() => setAction(undefined)} onUpdated={(updated, message) => { setSource(updated); setAction(undefined); setNotice(message); }} onDeleted={() => navigate(`/admin/assistants/${assistantId}/knowledge`)} />}</section>;
}

function SourceActionDialog({ action, source, assistantId, onClose, onUpdated, onDeleted }: { action: Action; source: KnowledgeSource; assistantId: string; onClose: () => void; onUpdated: (source: KnowledgeSource, message: string) => void; onDeleted: () => void }) {
  const auth = useAuth();
  const ref = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => ref.current?.showModal(), []);
  const label = action === 'reingest' ? 're-ingestion' : action === 'delete' ? 'deletion' : action;
  async function confirm() {
    setPending(true); setError('');
    try {
      if (action === 'delete') { await auth.api.deleteKnowledgeSource(assistantId, source.id); onDeleted(); return; }
      if (action === 'reingest') { const updated = await auth.api.reingestKnowledgeSource(assistantId, source.id); onUpdated(updated, updated.activeJobReused ? 'The active ingestion job was reused.' : 'Re-ingestion queued.'); return; }
      const state = action === 'disable' ? 'disabled' : 'enabled';
      const updated = await auth.api.updateKnowledgeSourceRetrieval(assistantId, source.id, state);
      onUpdated(updated, `Retrieval ${state}.`);
    } catch (e) {
      if (e instanceof AdminApiError && e.kind === 'unauthenticated') return auth.sessionExpired();
      if (action === 'delete' && e instanceof AdminApiError && e.kind === 'not_found') { onDeleted(); return; }
      setError(e instanceof AdminApiError && e.code === 'active_ingestion' ? 'This source cannot be deleted while ingestion is active.' : safeMessage(e)); setPending(false);
    }
  }
  return <dialog ref={ref} onCancel={onClose} aria-labelledby="source-dialog-title"><h2 id="source-dialog-title">Confirm {label}</h2><p>{action === 'disable' ? 'Stored knowledge remains present but will be excluded from retrieval.' : action === 'delete' ? `Delete ${source.name} and its owned indexed representation?` : action === 'reingest' ? 'Reprocess the persisted source without creating a duplicate.' : 'The currently committed knowledge may participate in retrieval.'}</p>{error && <p className="alert" role="alert">{error}</p>}<div className="dialog-actions"><button className={action === 'delete' ? 'danger' : ''} disabled={pending} onClick={confirm}>{pending ? 'Working…' : `Confirm ${label}`}</button><button disabled={pending} onClick={onClose}>Cancel</button></div></dialog>;
}
