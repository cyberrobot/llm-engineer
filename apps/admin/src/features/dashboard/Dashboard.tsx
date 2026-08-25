import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  AdminApiError,
  type OperationsHealth,
  type OperationsSummary,
} from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';

function errorMessage(error: unknown) {
  if (!(error instanceof AdminApiError)) return 'The dashboard could not be loaded. Try again.';
  if (error.kind === 'network') return 'The backend could not be reached. Try again.';
  if (error.kind === 'server') return 'The server could not complete the request. Try again.';
  if (error.kind === 'forbidden') return 'You do not have permission to view operational data.';
  if (error.kind === 'invalid_response') return 'The backend returned an invalid response.';
  return 'The dashboard could not be loaded. Try again.';
}

function formatDuration(seconds: number) {
  const wholeSeconds = Math.round(seconds);
  if (wholeSeconds < 60) return `${wholeSeconds} sec`;
  const wholeMinutes = Math.floor(wholeSeconds / 60);
  if (wholeMinutes < 60) return `${wholeMinutes} min`;
  const hours = Math.floor(wholeMinutes / 60);
  const minutes = wholeMinutes % 60;
  return minutes ? `${hours} hr ${minutes} min` : `${hours} hr`;
}

function healthLabel(health: OperationsHealth) {
  return health[0].toUpperCase() + health.slice(1);
}

function attentionConditions(summary: OperationsSummary) {
  const conditions: string[] = [];
  if (summary.health !== 'healthy') conditions.push(`Service health is ${summary.health}.`);
  if (summary.maintenance) conditions.push('Maintenance mode is enabled.');
  if (summary.jobs.failed > 0) conditions.push(`${summary.jobs.failed} operational ${summary.jobs.failed === 1 ? 'job has' : 'jobs have'} failed.`);
  if (summary.ingestion.failed > 0) conditions.push(`${summary.ingestion.failed} ingestion ${summary.ingestion.failed === 1 ? 'job has' : 'jobs have'} failed.`);
  if (summary.ingestion.recoverable > 0) conditions.push(`${summary.ingestion.recoverable} ingestion ${summary.ingestion.recoverable === 1 ? 'job is' : 'jobs are'} recoverable.`);
  if (summary.ingestion.queued > 0 && summary.ingestion.workersObserved === 0) conditions.push('Ingestion work is queued with no workers observed.');
  if (summary.knowledgeSources.failed !== null && summary.knowledgeSources.failed > 0) conditions.push(`${summary.knowledgeSources.failed} Knowledge ${summary.knowledgeSources.failed === 1 ? 'Source has' : 'Sources have'} failed.`);
  return conditions;
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SummaryCard({
  title,
  link,
  children,
}: {
  title: string;
  link?: { to: string; label: string };
  children: ReactNode;
}) {
  return (
    <section className="dashboard-card">
      <div className="dashboard-card-heading">
        <h2>{title}</h2>
        {link && <Link to={link.to}>{link.label}</Link>}
      </div>
      <dl className="dashboard-metrics">{children}</dl>
    </section>
  );
}

export function DashboardPage({ initialSummary }: { initialSummary?: OperationsSummary }) {
  const auth = useAuth();
  const [summary, setSummary] = useState<OperationsSummary | null>(initialSummary ?? null);
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (initialSummary) return;
    const controller = new AbortController();
    auth.api.getOperationsSummary(controller.signal).then(setSummary).catch((caught: unknown) => {
      if (caught instanceof DOMException && caught.name === 'AbortError') return;
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') {
        auth.sessionExpired();
        return;
      }
      setError(caught);
    });
    return () => controller.abort();
  }, [attempt, auth, initialSummary]);

  const refresh = () => {
    setError(undefined);
    setSummary(null);
    setAttempt((value) => value + 1);
  };

  if (error) {
    return (
      <section className="dashboard-state" aria-labelledby="dashboard-error-title">
        <h2 id="dashboard-error-title">Unable to load dashboard</h2>
        <p role="alert">{errorMessage(error)}</p>
        <button onClick={refresh}>Try again</button>
      </section>
    );
  }
  if (!summary) return <p role="status">Loading operational summary…</p>;

  const attention = attentionConditions(summary);
  return (
    <div className="dashboard">
      <div className="dashboard-intro">
        <p>Current operating state from the latest authoritative backend summary.</p>
        <button className="secondary-action" onClick={refresh}>Refresh dashboard</button>
      </div>

      <section className={`service-overview service-${summary.health}`} aria-labelledby="service-status-title">
        <div>
          <p className="eyebrow">Current state</p>
          <h2 id="service-status-title">Service status</h2>
        </div>
        <dl className="dashboard-metrics service-metrics">
          <Metric label="Overall health" value={healthLabel(summary.health)} />
          <Metric label="Maintenance" value={summary.maintenance ? 'Enabled' : 'Disabled'} />
          <div>
            <dt>Summary generated</dt>
            <dd><time dateTime={summary.generatedAt}>{new Date(summary.generatedAt).toLocaleString()}</time></dd>
          </div>
        </dl>
      </section>

      <section className={`attention-panel ${attention.length ? 'attention-required' : 'attention-clear'}`} aria-labelledby="attention-title">
        <h2 id="attention-title">Operational attention</h2>
        {attention.length ? (
          <ul>{attention.map((condition) => <li key={condition}>{condition}</li>)}</ul>
        ) : (
          <p role="status">No operational conditions currently require attention.</p>
        )}
      </section>

      <div className="dashboard-grid">
        <SummaryCard title="Assistants" link={{ to: '/admin/assistants', label: 'Manage Assistants' }}>
          <Metric label="Total" value={summary.assistants.total} />
          <Metric label="Published" value={summary.assistants.published} />
        </SummaryCard>
        <SummaryCard title="Knowledge Sources" link={{ to: '/admin/knowledge-sources', label: 'Manage Knowledge Sources' }}>
          <Metric label="Total" value={summary.knowledgeSources.total} />
          <Metric label="Enabled" value={summary.knowledgeSources.enabled} />
          <Metric label="Failed" value={summary.knowledgeSources.failed ?? 'Not reported'} />
        </SummaryCard>
        <SummaryCard title="Ingestion">
          <Metric label="Queued" value={summary.ingestion.queued} />
          <Metric label="Running" value={summary.ingestion.running} />
          <Metric label="Recoverable" value={summary.ingestion.recoverable} />
          <Metric label="Failed" value={summary.ingestion.failed} />
          <Metric label="Oldest queued age" value={formatDuration(summary.ingestion.oldestQueuedAgeSeconds)} />
          <Metric label="Workers observed" value={summary.ingestion.workersObserved} />
        </SummaryCard>
        <SummaryCard title="Operations">
          <Metric label="Cache regions" value={summary.cache.regions} />
          <Metric label="Running jobs" value={summary.jobs.running} />
          <Metric label="Failed jobs" value={summary.jobs.failed} />
          <Metric label="Administrative actions today" value={summary.audit.today} />
        </SummaryCard>
      </div>
    </div>
  );
}
