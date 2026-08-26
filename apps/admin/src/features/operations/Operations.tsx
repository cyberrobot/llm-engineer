import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  AdminApiError,
  type AuditDetail,
  type AuditOptions,
  type AuditPage,
  type AuditResult,
  type CacheRegion,
  type MaintenanceState,
  type OperationalJob,
  type OperationalJobs,
  type OperationalJobStatus,
  type OperationsHealth,
  type OperationsHealthDetail,
  type OperationsRoot,
} from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';

const PAGE_SIZE = 50;
const jobStatuses: OperationalJobStatus[] = ['queued', 'running', 'completed', 'failed', 'cancelled'];
const auditResults: AuditResult[] = ['STARTED', 'SUCCESS', 'FAILURE'];

function errorText(error: unknown, missing = 'The requested record was not found.') {
  if (!(error instanceof AdminApiError)) return 'The request could not be completed.';
  if (error.kind === 'forbidden') return 'You do not have permission to view or change this operational area.';
  if (error.kind === 'not_found') return missing;
  if (error.kind === 'invalid_response') return 'The backend returned an invalid response. No operational state has been inferred.';
  if (error.kind === 'network') return 'The backend could not be reached.';
  if (error.kind === 'server') return 'The backend could not complete the request.';
  if (error.kind === 'invalid_request') return 'The request was rejected as invalid.';
  return 'The request could not be completed.';
}

function useLoad<T>(loader: (signal: AbortSignal) => Promise<T>) {
  const auth = useAuth();
  const [state, setState] = useState<{ data?: T; error?: unknown; loading: boolean }>({ loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    loader(controller.signal).then((data) => setState({ data, loading: false })).catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      if (error instanceof AdminApiError && error.kind === 'unauthenticated') return auth.sessionExpired();
      setState((current) => ({ data: current.data, error, loading: false }));
    });
    return () => controller.abort();
  }, [attempt, auth, loader]);
  return { ...state, refresh: () => { setState((current) => ({ data: current.data, loading: true })); setAttempt((value) => value + 1); } };
}

function LoadState({ loading, error, hasData, retry }: { loading: boolean; error?: unknown; hasData: boolean; retry(): void }) {
  if (loading && !hasData) return <p role="status">Loading operational data…</p>;
  if (!error) return loading ? <p role="status">Refreshing operational data…</p> : null;
  return <div className="alert" role="alert"><p>{errorText(error)}</p><button onClick={retry}>Try again</button></div>;
}

function Status({ value }: { value: OperationsHealth | OperationalJobStatus | AuditResult }) {
  const label = value.toLowerCase().replace('_', ' ');
  return <span className={`badge status-${label}`}><span className="visually-hidden">Status: </span>{label[0]?.toUpperCase()}{label.slice(1)}</span>;
}

function dateTime(value: string | null) { return value ? new Date(value).toLocaleString() : 'Not available'; }
function duration(value: number | null) { return value === null ? 'Not available' : `${value.toLocaleString()} ms`; }
function metric(value: number | null, suffix = '') { return value === null ? 'Not available' : `${value.toLocaleString()}${suffix}`; }

type Confirmation = { title: string; description: ReactNode; confirmLabel: string; run(): Promise<void> };
function ConfirmationDialog({ confirmation, pending, error, onClose }: { confirmation: Confirmation; pending: boolean; error?: string; onClose(): void }) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { const previous=document.activeElement as HTMLElement|null; confirmRef.current?.focus(); return()=>previous?.focus(); }, []);
  return <dialog open aria-labelledby="operation-confirm-title" onCancel={(event) => { event.preventDefault(); if (!pending) onClose(); }}>
    <h2 id="operation-confirm-title">{confirmation.title}</h2>
    <p>{confirmation.description}</p>
    {error && <p className="alert" role="alert">{error}</p>}
    <div className="dialog-actions">
      <button className="secondary-action" disabled={pending} onClick={onClose}>Cancel</button>
      <button ref={confirmRef} className="danger" disabled={pending} onClick={confirmation.run}>{pending ? 'Working…' : confirmation.confirmLabel}</button>
    </div>
  </dialog>;
}

export function OperationsPage() {
  const auth = useAuth();
  const loader = useCallback((signal: AbortSignal) => auth.api.getOperations(signal), [auth.api]);
  const state = useLoad<OperationsRoot>(loader);
  const sections = [
    ['health', 'Health', '/admin/operations/health', 'Inspect application and dependency diagnostics.'],
    ['cache', 'Cache', '/admin/operations/cache', 'Inspect cache regions and perform confirmed administration.'],
    ['maintenance', 'Maintenance', '/admin/operations/maintenance', 'Inspect and deliberately change maintenance mode.'],
    ['jobs', 'Jobs', '/admin/operations/jobs', 'Browse operational background jobs.'],
    ['audit', 'Audit', '/admin/operations/audit', 'Browse administrative action history.'],
  ] as const;
  return <section className="operations-page">
    <p>Detailed operational inspection and administration. Production-affecting actions require confirmation.</p>
    <LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh} />
    {state.data && <div className="operations-grid">{sections.filter(([capability]) => state.data!.capabilities.includes(capability)).map(([capability, title, to, copy]) =>
      <section className="operations-card" key={capability}><h2>{title}</h2><p>{copy}</p><Link to={to}>Open {title}</Link></section>)}</div>}
  </section>;
}

export function OperationsHealthPage() {
  const auth = useAuth();
  const loader = useCallback((signal: AbortSignal) => auth.api.getOperationsHealth(signal), [auth.api]);
  const state = useLoad<OperationsHealthDetail>(loader);
  return <section className="operations-page"><div className="page-intro"><p>Authoritative dependency diagnostics supplied by the backend.</p><button disabled={state.loading} onClick={state.refresh}>{state.loading ? 'Refreshing…' : 'Refresh health'}</button></div>
    <LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh} />
    {state.data && <><section className={`operations-card health-${state.data.status}`}><h2>Overall health</h2><Status value={state.data.status}/><p>Checked {dateTime(state.data.generatedAt)}</p></section>
      {state.data.checks.length === 0 ? <section className="empty"><h2>No dependency checks</h2><p>The backend reported no registered checks.</p></section> : <div className="operations-grid">{state.data.checks.map((check) => <section className="operations-card" key={check.name}><h2>{check.name}</h2><Status value={check.status}/><dl><dt>Required</dt><dd>{check.required ? 'Yes' : 'No'}</dd><dt>Latency</dt><dd>{metric(check.latencyMs, ' ms')}</dd><dt>Diagnostic code</dt><dd>{check.code ?? 'None reported'}</dd><dt>Checked</dt><dd>{dateTime(check.checkedAt)}</dd></dl></section>)}</div>}</>}
  </section>;
}

export function OperationsCachePage() {
  const auth = useAuth();
  const loader = useCallback((signal: AbortSignal) => auth.api.listCacheRegions(signal), [auth.api]);
  const state = useLoad<CacheRegion[]>(loader);
  const [confirmation, setConfirmation] = useState<Confirmation>();
  const [pending, setPending] = useState(false);
  const [mutationError, setMutationError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [uncertain, setUncertain] = useState(false);
  const [region, setRegion] = useState('');
  const [key, setKey] = useState('');
  const trigger = (title: string, description: ReactNode, confirmLabel: string, action: () => Promise<unknown>, success: string) => {
    setMutationError(undefined);
    setConfirmation({ title, description, confirmLabel, run: async () => {
      if (pending) return;
      setPending(true);
      try { await action(); setConfirmation(undefined); setNotice(success); setKey(''); setUncertain(false); state.refresh(); }
      catch (error) {
        if (error instanceof AdminApiError && error.kind === 'unauthenticated') return auth.sessionExpired();
        if (error instanceof AdminApiError && error.kind === 'network') { setUncertain(true); setConfirmation(undefined); setMutationError(undefined); }
        else setMutationError(errorText(error));
      } finally { setPending(false); }
    }});
  };
  const invalidate = (event: FormEvent) => { event.preventDefault(); if (!region || !key || uncertain) return; const submittedRegion=region, submittedKey=key; trigger('Invalidate cache key', <>Invalidate the entered key in <strong>{submittedRegion}</strong>? The key value will not be retained after success.</>, 'Invalidate key', () => auth.api.invalidateCacheKey({region:submittedRegion,key:submittedKey}), 'Cache key invalidated. Cache state refreshed.'); };
  return <section className="operations-page"><div className="page-intro"><p>Statistics only; cache values are never exposed.</p><button disabled={state.loading} onClick={() => { setUncertain(false); state.refresh(); }}>Refresh cache</button></div>
    <LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{notice && <p className="success" role="status" tabIndex={-1}>{notice}</p>}{uncertain && <p className="alert" role="alert">The connection was lost after submission, so the outcome is unknown. Refresh authoritative cache state before trying another change.</p>}
    {state.data && <>{state.data.length === 0 ? <section className="empty"><h2>No cache regions</h2><p>No cache regions are registered.</p></section> : <div className="table-wrap"><table><caption className="visually-hidden">Registered cache region statistics</caption><thead><tr><th>Region</th><th>Entries</th><th>Memory</th><th>Hits</th><th>Misses</th><th>Hit ratio</th><th>Action</th></tr></thead><tbody>{state.data.map((item)=><tr key={item.name}><th scope="row">{item.name}</th><td>{metric(item.entries)}</td><td>{metric(item.estimatedMemoryBytes,' bytes')}</td><td>{metric(item.hitCount)}</td><td>{metric(item.missCount)}</td><td>{item.hitRatio===null?'Not available':`${(item.hitRatio*100).toFixed(1)}%`}</td><td><button className="danger-link" disabled={pending||uncertain} onClick={()=>{const selected=item.name;trigger('Clear cache region',<>Clear every entry in the <strong>{selected}</strong> cache region?</>,'Clear region',()=>auth.api.clearCacheRegion(selected),`${selected} cache region cleared. Cache state refreshed.`)}}>Clear {item.name}</button></td></tr>)}</tbody></table></div>}
      <section className="operations-card mutation-panel"><h2>Invalidate one key</h2><form className="operation-form" onSubmit={invalidate}><label>Region<select value={region} required onChange={(e)=>setRegion(e.target.value)}><option value="">Select a region</option>{state.data.map((item)=><option key={item.name}>{item.name}</option>)}</select></label><label>Cache key<input value={key} required maxLength={512} onChange={(e)=>setKey(e.target.value)}/></label><button disabled={pending||uncertain}>Review invalidation</button></form></section>
      <section className="operations-card danger-zone"><h2>Clear all cache regions</h2><p>This production-affecting action removes entries from every registered region.</p><button className="danger" disabled={pending||uncertain} onClick={()=>trigger('Clear all cache regions','Clear every entry from all registered cache regions?','Clear all regions',()=>auth.api.clearCache(),'All cache regions cleared. Cache state refreshed.')}>Clear all cache regions</button></section></>}
    {confirmation && <ConfirmationDialog confirmation={confirmation} pending={pending} error={mutationError} onClose={()=>!pending&&setConfirmation(undefined)}/>}</section>;
}

export function OperationsMaintenancePage() {
  const auth=useAuth(); const loader=useCallback((signal:AbortSignal)=>auth.api.getMaintenance(signal),[auth.api]); const state=useLoad<MaintenanceState>(loader);
  const messageRef=useRef<HTMLTextAreaElement>(null); const [confirmation,setConfirmation]=useState<Confirmation>(); const [pending,setPending]=useState(false); const [mutationError,setMutationError]=useState<string>(); const [notice,setNotice]=useState<string>(); const [uncertain,setUncertain]=useState(false);
  const prepare=(enabled:boolean)=>{const submittedMessage=enabled?(messageRef.current?.value||null):null;setMutationError(undefined);setConfirmation({title:enabled?'Enable maintenance mode':'Disable maintenance mode',description:enabled?'Enable maintenance mode and change production-facing application behaviour?':'Disable maintenance mode and restore normal application behaviour?',confirmLabel:enabled?'Enable maintenance':'Disable maintenance',run:async()=>{if(pending)return;setPending(true);try{await auth.api.updateMaintenance({enabled,message:submittedMessage});setConfirmation(undefined);setNotice(`Maintenance mode ${enabled?'enabled':'disabled'}. Authoritative state refreshed.`);setUncertain(false);state.refresh()}catch(error){if(error instanceof AdminApiError&&error.kind==='unauthenticated')return auth.sessionExpired();if(error instanceof AdminApiError&&error.kind==='network'){setUncertain(true);setConfirmation(undefined)}else setMutationError(errorText(error))}finally{setPending(false)}}})};
  return <section className="operations-page"><div className="page-intro"><p>Maintenance enforcement remains owned by the backend.</p><button disabled={state.loading} onClick={()=>{setUncertain(false);state.refresh()}}>Refresh state</button></div><LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{notice&&<p className="success" role="status">{notice}</p>}{uncertain&&<p className="alert" role="alert">The connection was lost after submission, so maintenance state may have changed. Refresh authoritative state before another update.</p>}
  {state.data&&<section className="operations-card"><h2>Current state: {state.data.enabled?'Enabled':'Disabled'}</h2><dl><dt>Message</dt><dd>{state.data.message??'No message'}</dd><dt>Updated</dt><dd>{dateTime(state.data.updatedAt)}</dd><dt>Updated by</dt><dd>{state.data.updatedBy??'Not reported'}</dd></dl><div className="operation-form"><label>Maintenance message<textarea key={`${state.data.updatedAt}:${state.data.enabled}`} ref={messageRef} maxLength={500} disabled={pending} defaultValue={state.data.message??''}/></label>{state.data.enabled?<button disabled={pending||uncertain} onClick={()=>prepare(false)}>Review disable</button>:<button className="danger" disabled={pending||uncertain} onClick={()=>prepare(true)}>Review enable</button>}</div></section>}
  {confirmation&&<ConfirmationDialog confirmation={confirmation} pending={pending} error={mutationError} onClose={()=>!pending&&setConfirmation(undefined)}/>}</section>;
}

function Pagination({ total, limit, offset, onPage }: { total:number;limit:number;offset:number;onPage(offset:number):void }) { return <nav className="pagination" aria-label="Result pages"><p>{total?`Showing ${offset+1}–${offset+Math.min(limit,total-offset)} of ${total}`:'0 results'}</p><div className="actions"><button disabled={offset===0} onClick={()=>onPage(Math.max(0,offset-limit))}>Previous</button><button disabled={offset+limit>=total} onClick={()=>onPage(offset+limit)}>Next</button></div></nav>; }
function JobTable({ page }: { page:OperationalJobs }) { return <div className="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Created</th><th>Duration</th><th>Retries</th><th>Node</th><th>Last error</th></tr></thead><tbody>{page.items.map((job)=><tr key={job.id}><td><Link to={`/admin/operations/jobs/${job.id}`}>{job.id}</Link></td><td>{job.jobType}</td><td><Status value={job.status}/></td><td>{dateTime(job.createdAt)}</td><td>{duration(job.durationMs)}</td><td>{job.retryCount}</td><td>{job.executionNode??'Not available'}</td><td>{job.lastError??'None'}</td></tr>)}</tbody></table></div>; }
export function OperationalJobsPage(){const auth=useAuth();const [params,setParams]=useSearchParams();const status=jobStatuses.includes(params.get('status') as OperationalJobStatus)?params.get('status') as OperationalJobStatus:undefined;const offset=Math.max(0,Number(params.get('offset'))||0);const loader=useCallback((signal:AbortSignal)=>auth.api.listOperationalJobs({limit:PAGE_SIZE,offset,status},signal),[auth.api,offset,status]);const state=useLoad<OperationalJobs>(loader);const update=(next:{status?:string;offset?:number})=>{const p=new URLSearchParams();const nextStatus=next.status??status;if(nextStatus)p.set('status',nextStatus);const nextOffset=next.offset??0;if(nextOffset)p.set('offset',String(nextOffset));setParams(p)};return <section className="operations-page"><div className="filters"><label>Status<select value={status??''} onChange={(e)=>update({status:e.target.value,offset:0})}><option value="">All statuses</option>{jobStatuses.map((value)=><option key={value}>{value}</option>)}</select></label></div><LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{state.data&&(state.data.items.length?<><JobTable page={state.data}/><Pagination {...state.data} onPage={(value)=>update({offset:value})}/></>:<section className="empty"><h2>No operational jobs</h2><p>No jobs match the current filter.</p></section>)}</section>}

function JobDetails({job}:{job:OperationalJob}){return <section className="operations-card detail"><Status value={job.status}/><dl><dt>Job ID</dt><dd>{job.id}</dd><dt>Job type</dt><dd>{job.jobType}</dd><dt>Created</dt><dd>{dateTime(job.createdAt)}</dd><dt>Started</dt><dd>{dateTime(job.startedAt)}</dd><dt>Completed</dt><dd>{dateTime(job.completedAt)}</dd><dt>Duration</dt><dd>{duration(job.durationMs)}</dd><dt>Retry count</dt><dd>{job.retryCount}</dd><dt>Execution node</dt><dd>{job.executionNode??'Not available'}</dd><dt>Last error</dt><dd>{job.lastError??'None'}</dd></dl></section>}
export function OperationalJobPage(){const {jobId=''}=useParams();const auth=useAuth();const loader=useCallback((signal:AbortSignal)=>auth.api.getOperationalJob(jobId,signal),[auth.api,jobId]);const state=useLoad<OperationalJob>(loader);return <section className="operations-page"><Link to="/admin/operations/jobs">Return to jobs</Link>{state.error instanceof AdminApiError&&state.error.kind==='not_found'?<section className="empty"><h2>Job not found</h2><p>{errorText(state.error,'This operational job does not exist.')}</p></section>:<><LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{state.data&&<JobDetails job={state.data}/>}</>}</section>}

function localDate(value:string){if(!value)return undefined;const parsed=new Date(value);return Number.isNaN(parsed.getTime())?undefined:parsed.toISOString()}
export function AuditPage(){const auth=useAuth();const [params,setParams]=useSearchParams();const [draft,setDraft]=useState(()=>({user:params.get('user')??'',action:params.get('action')??'',resource:params.get('resource')??'',result:params.get('result')??'',dateFrom:params.get('dateFrom')??'',dateTo:params.get('dateTo')??''}));const [rangeError,setRangeError]=useState('');const offset=Math.max(0,Number(params.get('offset'))||0);const options:AuditOptions={limit:PAGE_SIZE,offset,user:params.get('user')||undefined,action:params.get('action')||undefined,resource:params.get('resource')||undefined,result:auditResults.includes(params.get('result') as AuditResult)?params.get('result') as AuditResult:undefined,dateFrom:localDate(params.get('dateFrom')??''),dateTo:localDate(params.get('dateTo')??'')};const signature=JSON.stringify(options);const loader=useCallback((signal:AbortSignal)=>auth.api.listAuditEntries(JSON.parse(signature) as AuditOptions,signal),[auth.api,signature]);const state=useLoad<AuditPage>(loader);const submit=(event:FormEvent)=>{event.preventDefault();if(draft.dateFrom&&draft.dateTo&&draft.dateFrom>draft.dateTo){setRangeError('Date from must be before or equal to date to.');return}setRangeError('');const p=new URLSearchParams();Object.entries(draft).forEach(([key,value])=>{if(value)p.set(key,value)});setParams(p)};const page=(next:number)=>{const p=new URLSearchParams(params);if(next)p.set('offset',String(next));else p.delete('offset');setParams(p)};return <section className="operations-page"><form className="filters operation-filters" onSubmit={submit}><label>User<input value={draft.user} onChange={(e)=>setDraft({...draft,user:e.target.value})}/></label><label>Action<input value={draft.action} onChange={(e)=>setDraft({...draft,action:e.target.value})}/></label><label>Resource<input value={draft.resource} onChange={(e)=>setDraft({...draft,resource:e.target.value})}/></label><label>Result<select value={draft.result} onChange={(e)=>setDraft({...draft,result:e.target.value})}><option value="">All results</option>{auditResults.map((value)=><option key={value}>{value}</option>)}</select></label><label>Date from<input type="datetime-local" value={draft.dateFrom} onChange={(e)=>setDraft({...draft,dateFrom:e.target.value})}/></label><label>Date to<input type="datetime-local" value={draft.dateTo} onChange={(e)=>setDraft({...draft,dateTo:e.target.value})}/></label><button>Apply filters</button></form>{rangeError&&<p className="alert" role="alert">{rangeError}</p>}<LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{state.data&&(state.data.items.length?<><div className="table-wrap"><table><thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Resource</th><th>Result</th></tr></thead><tbody>{state.data.items.map((entry)=><tr key={entry.id}><td><Link to={`/admin/operations/audit/${entry.id}`}>{dateTime(entry.timestamp)}</Link></td><td>{entry.user}</td><td>{entry.action}</td><td>{entry.resource}</td><td><Status value={entry.result}/></td></tr>)}</tbody></table></div><Pagination {...state.data} onPage={page}/></>:<section className="empty"><h2>No audit entries</h2><p>No entries match the current filters.</p></section>)}</section>}

export function AuditDetailPage(){const {entryId=''}=useParams();const auth=useAuth();const loader=useCallback((signal:AbortSignal)=>auth.api.getAuditEntry(entryId,signal),[auth.api,entryId]);const state=useLoad<AuditDetail>(loader);return <section className="operations-page"><Link to="/admin/operations/audit">Return to audit log</Link>{state.error instanceof AdminApiError&&state.error.kind==='not_found'?<section className="empty"><h2>Audit entry not found</h2><p>This administrative audit entry does not exist.</p></section>:<><LoadState {...state} hasData={Boolean(state.data)} retry={state.refresh}/>{state.data&&<section className="operations-card detail"><Status value={state.data.result}/><dl><dt>Timestamp</dt><dd>{dateTime(state.data.timestamp)}</dd><dt>User</dt><dd>{state.data.user}</dd><dt>Actor</dt><dd>{state.data.actor}</dd><dt>Action</dt><dd>{state.data.action}</dd><dt>Resource</dt><dd>{state.data.resource}</dd><dt>Duration</dt><dd>{duration(state.data.durationMs)}</dd><dt>Request ID</dt><dd>{state.data.requestId}</dd><dt>Correlation ID</dt><dd>{state.data.correlationId}</dd></dl><h2>Metadata</h2><pre className="metadata">{JSON.stringify(state.data.metadata,null,2)}</pre></section>}</>}</section>}
