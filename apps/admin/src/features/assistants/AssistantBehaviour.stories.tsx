import type { Meta, StoryObj } from '@storybook/react-vite';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { expect, userEvent, within } from 'storybook/test';
import {
  AdminApiError,
  createAdminApi,
  type AdminApi,
  type AssistantBehaviour,
  type AssistantDetail,
} from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import { AssistantBehaviourPage, AssistantPreviewPage } from './AssistantBehaviour';

const assistant: AssistantDetail = {
  id: '11111111-1111-4111-8111-111111111111',
  slug: 'fictional-policy',
  name: 'Fictional policy assistant',
  status: 'inactive',
  visibility: 'private',
  createdAt: '2026-08-01T09:00:00Z',
  updatedAt: '2026-08-10T09:00:00Z',
  concurrencyToken: '2026-08-10T09:00:00Z',
  knowledgeSourceCount: 2,
  deletionAllowed: false,
};

const behaviour: AssistantBehaviour = {
  assistantId: assistant.id,
  draft: {
    revision: 2,
    instructions: 'Answer questions using only the fictional policy.\n\nState uncertainty clearly.',
    welcomeMessage: 'Welcome. I can help with the fictional policy.',
    inputPlaceholder: 'Ask about the fictional policy',
    suggestedQuestions: ['What does the policy cover?', 'How can I appeal?'],
    createdAt: '2026-08-10T09:00:00Z',
  },
  published: { revision: 1, publishedAt: '2026-08-09T12:00:00Z' },
  hasUnpublishedChanges: true,
  concurrencyToken: '2',
};

const base: AdminApi = {
  ...createAdminApi(''),
  currentUser: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
  login: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
  logout: async () => undefined,
  getOperationsSummary: async () => ({ generatedAt:'2026-08-25T10:00:00Z',health:'healthy',maintenance:false,cache:{regions:0},jobs:{running:0,failed:0},audit:{today:0},assistants:{total:0,published:0},knowledgeSources:{total:0,enabled:0,failed:null},ingestion:{queued:0,running:0,recoverable:0,failed:0,oldestQueuedAgeSeconds:0,workersObserved:0} }),
  listAssistants: async () => ({ items: [assistant], total: 1, limit: 50, offset: 0 }),
  getAssistant: async () => assistant,
  createAssistant: async () => assistant,
  updateAssistant: async () => assistant,
  deleteAssistant: async () => undefined,
  getAssistantBehaviour: async () => behaviour,
  updateAssistantBehaviour: async () => ({ ...behaviour, concurrencyToken: '3', draft: { ...behaviour.draft, revision: 3 } }),
  publishAssistantBehaviour: async () => ({ ...behaviour, published: { revision: 2, publishedAt: '2026-08-10T10:00:00Z' }, hasUnpublishedChanges: false, concurrencyToken: '3' }),
  previewAssistantMessage: async (_id, _input, options) => {
    const answer = 'This is a deterministic fictional answer.';
    options?.onDelta?.(answer);
    return { answer };
  },
  listKnowledgeSources: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
  getKnowledgeSource: async () => { throw new AdminApiError('not_found'); },
  createKnowledgeSource: async () => { throw new AdminApiError('invalid_request'); },
  updateKnowledgeSourceRetrieval: async () => { throw new AdminApiError('invalid_request'); },
  reingestKnowledgeSource: async () => { throw new AdminApiError('invalid_request'); },
  deleteKnowledgeSource: async () => undefined,
};

function Frame({ api = base, preview = false }: { api?: AdminApi; preview?: boolean }) {
  const path = `/admin/assistants/${assistant.id}/${preview ? 'preview' : 'behaviour'}`;
  const router = createMemoryRouter([{
    path: '/admin/assistants/:assistantId/:section',
    element: (
      <AuthProvider api={api} initialUser={{ id: 'admin', email: 'admin@example.test', role: 'administrator' }}>
        {preview ? <AssistantPreviewPage /> : <AssistantBehaviourPage />}
      </AuthProvider>
    ),
  }], { initialEntries: [path] });
  return <RouterProvider router={router} />;
}

const meta = { title: 'Assistants/Behaviour and preview' } satisfies Meta;
export default meta;
type Story = StoryObj;

export const BehaviourLoaded: Story = { render: () => <Frame /> };
export const UnsavedBehaviourEdits: Story = {
  render: () => <Frame />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByLabelText('Instructions'), ' Additional guidance.');
    await expect(canvas.getByText('Save your local edits before previewing or publishing them.')).toBeInTheDocument();
  },
};
export const ValidationError: Story = {
  render: () => <Frame />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.clear(await canvas.findByLabelText('Instructions'));
    await userEvent.click(canvas.getByRole('button', { name: 'Save draft' }));
    await expect(canvas.getByRole('alert')).toHaveTextContent('Instructions are required.');
  },
};
export const SavePending: Story = {
  render: () => <Frame api={{ ...base, updateAssistantBehaviour: () => new Promise(() => undefined) }} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByLabelText('Instructions'), ' Pending.');
    await userEvent.click(canvas.getByRole('button', { name: 'Save draft' }));
    await expect(canvas.getByRole('button', { name: 'Saving draft…' })).toBeDisabled();
  },
};
export const SaveSuccess: Story = {
  render: () => <Frame />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByLabelText('Instructions'), ' Confirmed.');
    await userEvent.click(canvas.getByRole('button', { name: 'Save draft' }));
    await expect(canvas.getByRole('status')).toHaveTextContent('Behaviour draft saved.');
  },
};
export const StaleUpdateConflict: Story = {
  render: () => <Frame api={{ ...base, updateAssistantBehaviour: async () => { throw new AdminApiError('conflict', 'assistant_behaviour_update_conflict'); } }} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByLabelText('Instructions'), ' Stale.');
    await userEvent.click(canvas.getByRole('button', { name: 'Save draft' }));
    await expect(canvas.getByRole('alert')).toHaveTextContent('changed elsewhere');
  },
};
export const UnpublishedDraft: Story = { render: () => <Frame api={{ ...base, getAssistantBehaviour: async () => ({ ...behaviour, published: null }) }} /> };
export const PublishedConfiguration: Story = { render: () => <Frame api={{ ...base, getAssistantBehaviour: async () => ({ ...behaviour, published: { revision: 2, publishedAt: '2026-08-10T10:00:00Z' }, hasUnpublishedChanges: false }) }} /> };
export const DraftChangesAwaitingPublication: Story = { render: () => <Frame /> };
export const PublishConfirmation: Story = {
  render: () => <Frame />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Publish saved draft' }));
    await expect(canvas.getByRole('dialog')).toHaveTextContent('Publication does not change lifecycle settings.');
  },
};
export const PublishPending: Story = {
  render: () => <Frame api={{ ...base, publishAssistantBehaviour: () => new Promise(() => undefined) }} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Publish saved draft' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm publication' }));
    await expect(canvas.getByRole('button', { name: 'Publishing…' })).toBeDisabled();
  },
};
export const PublishSuccess: Story = {
  render: () => <Frame />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Publish saved draft' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm publication' }));
    await expect(canvas.getByText('Behaviour published successfully.')).toBeInTheDocument();
  },
};
export const PreviewInitialState: Story = { render: () => <Frame preview /> };
export const PreviewConversation: Story = {
  render: () => <Frame preview />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByPlaceholderText('Ask about the fictional policy'), 'What is fictional?{Enter}');
    await expect(canvas.getByText('This is a deterministic fictional answer.')).toBeInTheDocument();
  },
};
export const PreviewRequestPending: Story = {
  render: () => <Frame preview api={{ ...base, previewAssistantMessage: () => new Promise(() => undefined) }} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByPlaceholderText('Ask about the fictional policy'), 'Pending question{Enter}');
    await expect(canvas.getByText('Thinking…')).toBeInTheDocument();
  },
};
export const PreviewSafeFailure: Story = {
  render: () => <Frame preview api={{ ...base, previewAssistantMessage: async () => { throw new AdminApiError('network'); } }} />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.type(await canvas.findByPlaceholderText('Ask about the fictional policy'), 'Fail safely{Enter}');
    await expect(canvas.getByRole('alert')).toHaveTextContent("couldn't reach the assistant");
  },
};
