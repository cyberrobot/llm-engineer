import {
  AssistantChatError,
  AssistantWidgetConversation,
  type AssistantChatClient,
} from '@redmoor/assistant-widget';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  Link,
  NavLink,
  unstable_usePrompt as usePrompt,
  useBeforeUnload,
  useParams,
} from 'react-router-dom';
import {
  AdminApiError,
  type AssistantBehaviour,
  type AssistantDetail,
} from '../../api/adminApi';
import { useAuth } from '../../auth/AuthContext';

const LIMITS = {
  instructions: 12_000,
  welcomeMessage: 1_000,
  inputPlaceholder: 160,
  questions: 8,
  question: 240,
} as const;

type FormValues = {
  instructions: string;
  welcomeMessage: string;
  inputPlaceholder: string;
  suggestedQuestions: string[];
};

function valuesFrom(behaviour: AssistantBehaviour): FormValues {
  return {
    instructions: behaviour.draft.instructions,
    welcomeMessage: behaviour.draft.welcomeMessage,
    inputPlaceholder: behaviour.draft.inputPlaceholder,
    suggestedQuestions: [...behaviour.draft.suggestedQuestions],
  };
}

function sameValues(left: FormValues, right: FormValues) {
  return left.instructions === right.instructions &&
    left.welcomeMessage === right.welcomeMessage &&
    left.inputPlaceholder === right.inputPlaceholder &&
    left.suggestedQuestions.length === right.suggestedQuestions.length &&
    left.suggestedQuestions.every((question, index) => question === right.suggestedQuestions[index]);
}

function safeMessage(error: unknown) {
  if (!(error instanceof AdminApiError)) return 'The request could not be completed.';
  if (error.kind === 'network') return 'The backend could not be reached. Try again.';
  if (error.kind === 'server') return 'The server could not complete the request. Try again.';
  if (error.kind === 'invalid_response') return 'The backend returned an invalid response.';
  if (error.kind === 'forbidden') return 'You do not have permission to manage this assistant.';
  return 'The request could not be completed.';
}

function validate(values: FormValues): string {
  if (!values.instructions.trim()) return 'Instructions are required.';
  if (values.instructions.length > LIMITS.instructions) return `Instructions must be ${LIMITS.instructions.toLocaleString()} characters or fewer.`;
  if (values.welcomeMessage.length > LIMITS.welcomeMessage) return `Welcome message must be ${LIMITS.welcomeMessage.toLocaleString()} characters or fewer.`;
  if (!values.inputPlaceholder.trim()) return 'Input placeholder is required.';
  if (values.inputPlaceholder.length > LIMITS.inputPlaceholder) return `Input placeholder must be ${LIMITS.inputPlaceholder} characters or fewer.`;
  if (/\r|\n|\t/.test(values.inputPlaceholder)) return 'Input placeholder must be one line.';
  if (values.suggestedQuestions.length > LIMITS.questions) return `Use no more than ${LIMITS.questions} suggested questions.`;
  const empty = values.suggestedQuestions.findIndex((question) => !question.trim());
  if (empty >= 0) return `Suggested question ${empty + 1} must not be empty.`;
  const long = values.suggestedQuestions.findIndex((question) => question.length > LIMITS.question);
  if (long >= 0) return `Suggested question ${long + 1} must be ${LIMITS.question} characters or fewer.`;
  if (values.suggestedQuestions.some((question) => /\r|\n|\t/.test(question))) return 'Suggested questions must each be one line.';
  return '';
}

export function AssistantNavigation({ assistant }: { assistant: AssistantDetail }) {
  const root = `/admin/assistants/${assistant.id}`;
  return (
    <>
      <div className="assistant-heading">
        <div>
          <p className="eyebrow">Assistant</p>
          <h2>{assistant.name}</h2>
        </div>
        <div className="assistant-lifecycle" aria-label="Assistant availability settings">
          <span>{assistant.status === 'active' ? 'Active' : 'Inactive'}</span>
          <span>{assistant.visibility === 'public' ? 'Public' : 'Private'}</span>
        </div>
      </div>
      <nav className="assistant-navigation" aria-label={`${assistant.name} sections`}>
        <NavLink to={`${root}/edit`}>General</NavLink>
        <NavLink to={`${root}/behaviour`}>Behaviour</NavLink>
        <NavLink to={`${root}/knowledge`}>Knowledge</NavLink>
        <NavLink to={`${root}/preview`}>Preview</NavLink>
      </nav>
    </>
  );
}

type LoadedWorkspace = { assistant: AssistantDetail; behaviour: AssistantBehaviour };

function useWorkspace(assistantId: string | undefined) {
  const auth = useAuth();
  const [state, setState] = useState<LoadedWorkspace>();
  const [error, setError] = useState<unknown>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!assistantId) return;
    const controller = new AbortController();
    Promise.all([
      auth.api.getAssistant(assistantId, controller.signal),
      auth.api.getAssistantBehaviour(assistantId, controller.signal),
    ]).then(([assistant, behaviour]) => setState({ assistant, behaviour })).catch((caught: unknown) => {
      if (caught instanceof DOMException && caught.name === 'AbortError') return;
      if (caught instanceof AdminApiError && caught.kind === 'unauthenticated') auth.sessionExpired();
      else setError(caught);
    });
    return () => controller.abort();
  }, [assistantId, attempt, auth]);
  return {
    state,
    error,
    retry() {
      setState(undefined);
      setError(undefined);
      setAttempt((value) => value + 1);
    },
  };
}

function WorkspaceState({ error, retry }: { error: unknown; retry: () => void }) {
  if (error instanceof AdminApiError && error.kind === 'not_found') {
    return (
      <section className="empty" role="alert">
        <h2>Assistant not found</h2>
        <p>The requested assistant does not exist.</p>
        <Link to="/admin/assistants">Return to assistants</Link>
      </section>
    );
  }
  return (
    <section className="empty" role="alert">
      <h2>Unable to load assistant behaviour</h2>
      <p>{safeMessage(error)}</p>
      <button onClick={retry}>Try again</button>
    </section>
  );
}

export function AssistantBehaviourPage() {
  const { assistantId } = useParams();
  const workspace = useWorkspace(assistantId);
  if (workspace.error) return <WorkspaceState error={workspace.error} retry={workspace.retry} />;
  if (!workspace.state || !assistantId) return <p role="status">Loading assistant behaviour…</p>;
  return (
    <AssistantBehaviourEditor
      key={`${workspace.state.behaviour.concurrencyToken}:${workspace.state.behaviour.draft.revision}`}
      assistant={workspace.state.assistant}
      assistantId={assistantId}
      initialBehaviour={workspace.state.behaviour}
    />
  );
}

function AssistantBehaviourEditor({ assistant, assistantId, initialBehaviour }: {
  assistant: AssistantDetail;
  assistantId: string;
  initialBehaviour: AssistantBehaviour;
}) {
  const auth = useAuth();
  const [server, setServer] = useState(initialBehaviour);
  const [values, setValues] = useState(() => valuesFrom(initialBehaviour));
  const [savePending, setSavePending] = useState(false);
  const [publishPending, setPublishPending] = useState(false);
  const [refreshPending, setRefreshPending] = useState(false);
  const [notice, setNotice] = useState('');
  const [formError, setFormError] = useState('');
  const [publishOpen, setPublishOpen] = useState(false);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const publishButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (notice || formError) feedbackRef.current?.focus();
  }, [formError, notice]);

  const dirty = !sameValues(values, valuesFrom(server));
  usePrompt({ message: 'Discard your unsaved behaviour changes?', when: dirty });
  useBeforeUnload((event) => { if (dirty) event.preventDefault(); }, { capture: true });

  const confirmedServer = server;
  const currentValues = values;
  const currentAssistantId = assistantId;

  function change<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((current) => current ? { ...current, [key]: value } : current);
    setNotice('');
    setFormError('');
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (savePending || publishPending) return;
    const invalid = validate(currentValues);
    if (invalid) {
      setFormError(invalid);
      setNotice('');
      return;
    }
    setSavePending(true);
    setFormError('');
    setNotice('');
    try {
      const confirmed = await auth.api.updateAssistantBehaviour(currentAssistantId, {
        concurrency_token: confirmedServer.concurrencyToken,
        instructions: currentValues.instructions,
        welcome_message: currentValues.welcomeMessage,
        input_placeholder: currentValues.inputPlaceholder,
        suggested_questions: [...currentValues.suggestedQuestions],
      });
      setServer(confirmed);
      setValues(valuesFrom(confirmed));
      setNotice('Behaviour draft saved.');
    } catch (error) {
      if (error instanceof AdminApiError && error.kind === 'unauthenticated') return auth.sessionExpired();
      setFormError(error instanceof AdminApiError && error.code === 'assistant_behaviour_update_conflict'
        ? 'This behaviour changed elsewhere. Your edits are preserved; refresh before saving again.'
        : safeMessage(error));
    } finally {
      setSavePending(false);
    }
  }

  async function publish() {
    if (publishPending || savePending) return;
    setPublishPending(true);
    setFormError('');
    try {
      const confirmed = await auth.api.publishAssistantBehaviour(currentAssistantId, {
        concurrency_token: confirmedServer.concurrencyToken,
        draft_revision: confirmedServer.draft.revision,
      });
      setServer(confirmed);
      setValues(valuesFrom(confirmed));
      setPublishOpen(false);
      setNotice('Behaviour published successfully.');
    } catch (error) {
      if (error instanceof AdminApiError && error.kind === 'unauthenticated') return auth.sessionExpired();
      setPublishOpen(false);
      setFormError(error instanceof AdminApiError && error.code === 'assistant_behaviour_publish_conflict'
        ? 'The saved draft changed before publication. Refresh and review the current draft before publishing.'
        : safeMessage(error));
    } finally {
      setPublishPending(false);
    }
  }

  async function refresh() {
    if (dirty && !window.confirm('Discard your unsaved behaviour changes and reload from the server?')) return;
    if (refreshPending) return;
    setRefreshPending(true);
    setNotice('');
    setFormError('');
    try {
      const confirmed = await auth.api.getAssistantBehaviour(currentAssistantId);
      setServer(confirmed);
      setValues(valuesFrom(confirmed));
      setNotice('Behaviour refreshed from the server.');
    } catch (error) {
      if (error instanceof AdminApiError && error.kind === 'unauthenticated') return auth.sessionExpired();
      setFormError(safeMessage(error));
    } finally {
      setRefreshPending(false);
    }
  }

  return (
    <section className="assistant-workspace">
      <AssistantNavigation assistant={assistant} />
      {(notice || formError) && (
        <div ref={feedbackRef} tabIndex={-1} className={notice ? 'success' : 'alert'} role={notice ? 'status' : 'alert'}>
          {notice || formError}
          {formError.toLowerCase().includes('refresh') && <button disabled={refreshPending} className="link-button feedback-action" onClick={refresh}>{refreshPending ? 'Refreshing…' : 'Refresh server state'}</button>}
        </div>
      )}
      <div className="behaviour-layout">
        <form className="assistant-form behaviour-form" onSubmit={save} noValidate>
          <div>
            <h3>Behaviour</h3>
            <p>Instructions control generated answers. Conversation text is displayed directly to users.</p>
          </div>
          <label>
            Instructions
            <span className="field-help">Describe how the Assistant should answer, what role it performs, and what it should avoid claiming.</span>
            <textarea aria-label="Instructions" rows={12} maxLength={LIMITS.instructions} value={values.instructions} onChange={(event) => change('instructions', event.target.value)} />
            <span className="character-count">{values.instructions.length.toLocaleString()} / {LIMITS.instructions.toLocaleString()}</span>
          </label>
          <label>
            Welcome message
            <textarea aria-label="Welcome message" rows={3} maxLength={LIMITS.welcomeMessage} value={values.welcomeMessage} onChange={(event) => change('welcomeMessage', event.target.value)} />
            <span className="character-count">{values.welcomeMessage.length.toLocaleString()} / {LIMITS.welcomeMessage.toLocaleString()}</span>
          </label>
          <label>
            Input placeholder
            <input aria-label="Input placeholder" maxLength={LIMITS.inputPlaceholder} value={values.inputPlaceholder} onChange={(event) => change('inputPlaceholder', event.target.value)} />
          </label>
          <fieldset className="suggested-question-editor">
            <legend>Suggested questions</legend>
            <p className="field-help">Optional starting questions, displayed in this order.</p>
            {values.suggestedQuestions.map((question, index) => (
              <div className="suggested-question-row" key={index}>
                <label>
                  Question {index + 1}
                  <input maxLength={LIMITS.question} value={question} onChange={(event) => {
                    const next = [...values.suggestedQuestions];
                    next[index] = event.target.value;
                    change('suggestedQuestions', next);
                  }} />
                </label>
                <div className="question-actions">
                  <button type="button" className="secondary-action" disabled={index === 0} aria-label={`Move question ${index + 1} up`} onClick={() => {
                    const next = [...values.suggestedQuestions];
                    [next[index - 1], next[index]] = [next[index], next[index - 1]];
                    change('suggestedQuestions', next);
                  }}>Move up</button>
                  <button type="button" className="secondary-action" disabled={index === values.suggestedQuestions.length - 1} aria-label={`Move question ${index + 1} down`} onClick={() => {
                    const next = [...values.suggestedQuestions];
                    [next[index], next[index + 1]] = [next[index + 1], next[index]];
                    change('suggestedQuestions', next);
                  }}>Move down</button>
                  <button type="button" className="danger-link" aria-label={`Remove question ${index + 1}`} onClick={() => change('suggestedQuestions', values.suggestedQuestions.filter((_item, itemIndex) => itemIndex !== index))}>Remove</button>
                </div>
              </div>
            ))}
            <button type="button" className="secondary-action add-question" disabled={values.suggestedQuestions.length >= LIMITS.questions} onClick={() => change('suggestedQuestions', [...values.suggestedQuestions, ''])}>Add question</button>
          </fieldset>
          <div className="form-actions">
            <button disabled={savePending || publishPending || !dirty}>{savePending ? 'Saving draft…' : 'Save draft'}</button>
            <Link to={`/admin/assistants/${assistant.id}/preview`}>Preview saved draft</Link>
          </div>
        </form>
        <aside className="publication-card" aria-labelledby="publication-title">
          <h3 id="publication-title">Publishing</h3>
          <p className="publication-state"><strong>{server.hasUnpublishedChanges ? 'Draft changes awaiting publication' : 'Draft matches published configuration'}</strong></p>
          {server.published ? (
            <p>Revision {server.published.revision} published {new Date(server.published.publishedAt).toLocaleString()}.</p>
          ) : <p>This Assistant has never been published.</p>}
          <p>{assistant.status === 'active' && assistant.visibility === 'public'
            ? 'Publishing updates the configuration used by this currently active, public Assistant.'
            : `Publishing configuration does not make the Assistant available. It remains ${assistant.status} and ${assistant.visibility}.`}</p>
          {dirty && <p className="draft-warning">Save your local edits before previewing or publishing them.</p>}
          <button ref={publishButtonRef} disabled={dirty || !server.hasUnpublishedChanges || savePending || publishPending} onClick={() => setPublishOpen(true)}>Publish saved draft</button>
        </aside>
      </div>
      {publishOpen && (
        <PublishDialog
          assistant={assistant}
          pending={publishPending}
          onCancel={() => {
            setPublishOpen(false);
            window.setTimeout(() => publishButtonRef.current?.focus(), 0);
          }}
          onConfirm={publish}
        />
      )}
    </section>
  );
}

function PublishDialog({ assistant, pending, onCancel, onConfirm }: {
  assistant: AssistantDetail;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onCancel={(event) => { event.preventDefault(); if (!pending) onCancel(); }} aria-labelledby="publish-title">
      <h2 id="publish-title">Publish {assistant.name}?</h2>
      <p>The saved draft configuration will become the configuration used by public conversations.</p>
      <p>Publication does not change lifecycle settings. This Assistant will remain {assistant.status} and {assistant.visibility}.</p>
      <div className="dialog-actions">
        <button disabled={pending} onClick={onConfirm}>{pending ? 'Publishing…' : 'Confirm publication'}</button>
        <button disabled={pending} onClick={onCancel}>Cancel</button>
      </div>
      <p className="visually-hidden" role="status">{pending ? 'Publication in progress' : ''}</p>
    </dialog>
  );
}

export function AssistantPreviewPage() {
  const auth = useAuth();
  const { assistantId } = useParams();
  const workspace = useWorkspace(assistantId);
  const [reset, setReset] = useState(0);
  const chatClient = useMemo<AssistantChatClient | undefined>(() => {
    if (!assistantId) return undefined;
    return {
      historyLimit: 12,
      async send(request, { signal }) {
        try {
          return await auth.api.previewAssistantMessage(assistantId, {
            message: request.message,
            history: request.history.map((item) => ({ role: item.role, content: item.content })),
          }, signal);
        } catch (error) {
          if (error instanceof AdminApiError && error.kind === 'unauthenticated') auth.sessionExpired();
          if (error instanceof AdminApiError && error.kind === 'invalid_request') throw new AssistantChatError('invalid_request', false);
          if (error instanceof AdminApiError && ['not_found', 'conflict', 'forbidden'].includes(error.kind)) throw new AssistantChatError('assistant_unavailable', false);
          if (error instanceof AdminApiError && error.kind === 'network') throw new AssistantChatError('network_error', true);
          if (error instanceof AdminApiError && error.kind === 'invalid_response') throw new AssistantChatError('invalid_response', true);
          throw new AssistantChatError('server_error', true);
        }
      },
    };
  }, [assistantId, auth]);

  if (workspace.error) return <WorkspaceState error={workspace.error} retry={workspace.retry} />;
  if (!workspace.state || !chatClient) return <p role="status">Loading assistant preview…</p>;
  const { assistant, behaviour } = workspace.state;
  return (
    <section className="assistant-workspace">
      <AssistantNavigation assistant={assistant} />
      <div className="preview-intro">
        <div>
          <h3>Preview</h3>
          <p><strong>Previewing saved draft revision {behaviour.draft.revision}.</strong> Unsaved Behaviour edits are never included.</p>
        </div>
        <button className="secondary-action" onClick={() => setReset((value) => value + 1)}>Reset conversation</button>
      </div>
      <div className="assistant-preview-frame">
        <AssistantWidgetConversation
          key={reset}
          assistantName={assistant.name}
          chatClient={chatClient}
          placeholder={behaviour.draft.inputPlaceholder}
          suggestedQuestions={behaviour.draft.suggestedQuestions}
          welcomeMessage={behaviour.draft.welcomeMessage}
        />
      </div>
    </section>
  );
}
