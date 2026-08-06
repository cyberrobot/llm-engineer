import type { Meta, StoryObj } from '@storybook/react-vite';
import type { ReactNode } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { expect, userEvent, within } from 'storybook/test';
import { AdminApiError, type AdminApi, type Assistant, type KnowledgeSource } from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import {
  KnowledgeEntryPage,
  KnowledgeSourceCreatePage,
  KnowledgeSourceDetailPage,
  KnowledgeSourcesPage,
} from './KnowledgeSources';

const assistant: Assistant = {
  id: '11111111-1111-4111-8111-111111111111',
  slug: 'legal-review',
  name: 'Legal review',
  status: 'inactive',
  visibility: 'private',
  createdAt: '2026-08-01T09:00:00Z',
  updatedAt: '2026-08-04T09:00:00Z',
  concurrencyToken: '2026-08-04T09:00:00Z',
};
const source: KnowledgeSource = {
  id: '22222222-2222-4222-8222-222222222222',
  assistantId: assistant.id,
  sourceType: 'direct_text',
  name: 'Policy guide',
  retrievalState: 'enabled',
  url: null,
  directText: 'Fictional policy content.',
  documentId: 'document-1',
  createdAt: '2026-08-04T09:00:00Z',
  updatedAt: '2026-08-04T10:00:00Z',
  latestIngestion: {
    id: '33333333-3333-4333-8333-333333333333',
    status: 'completed',
    currentStep: null,
    createdAt: '2026-08-04T09:00:00Z',
    startedAt: '2026-08-04T09:01:00Z',
    completedAt: '2026-08-04T09:02:00Z',
    failureCode: null,
    failureMessage: null,
  },
  activeJobReused: false,
};
const summary = { ...source, directText: null };
const base: AdminApi = {
  currentUser: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
  login: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
  logout: async () => undefined,
  listAssistants: async () => ({ items: [assistant], total: 1, limit: 100, offset: 0 }),
  getAssistant: async () => ({ ...assistant, knowledgeSourceCount: 1, deletionAllowed: false }),
  createAssistant: async () => assistant,
  updateAssistant: async () => assistant,
  deleteAssistant: async () => undefined,
  listKnowledgeSources: async () => ({
    items: [
      summary,
      {
        ...summary,
        id: '44444444-4444-4444-8444-444444444444',
        sourceType: 'url',
        name: 'Public guide',
        url: 'https://example.test/guide',
      },
    ],
    total: 2,
    limit: 50,
    offset: 0,
  }),
  getKnowledgeSource: async () => source,
  createKnowledgeSource: async () => source,
  updateKnowledgeSourceRetrieval: async () => ({ ...source, retrievalState: 'disabled' }),
  reingestKnowledgeSource: async () => ({ ...source, activeJobReused: true }),
  deleteKnowledgeSource: async () => undefined,
};

type StoryLocation = string | { pathname: string; state: unknown };
function Frame({
  children,
  api = base,
  path,
  route = '*',
}: {
  children: ReactNode;
  api?: AdminApi;
  path: StoryLocation;
  route?: string;
}) {
  const router = createMemoryRouter(
    [{
      path: route,
      element: (
        <AuthProvider api={api} initialUser={{ id: 'admin', email: 'admin@example.test', role: 'administrator' }}>
          {children}
        </AuthProvider>
      ),
    }],
    { initialEntries: [path] },
  );
  return <RouterProvider router={router} />;
}

const listPath = `/admin/assistants/${assistant.id}/knowledge`;
const detailPath = `${listPath}/${source.id}`;
const listRoute = '/admin/assistants/:assistantId/knowledge';
const detailRoute = '/admin/assistants/:assistantId/knowledge/:sourceId';
const createRoute = '/admin/assistants/:assistantId/knowledge/new';

const meta = { title: 'Knowledge/Management' } satisfies Meta;
export default meta;
type Story = StoryObj;

export const AssistantSelection: Story = {
  render: () => <Frame path="/admin/knowledge-sources"><KnowledgeEntryPage /></Frame>,
};
export const PopulatedList: Story = {
  render: () => <Frame path={listPath} route={listRoute}><KnowledgeSourcesPage /></Frame>,
};
export const EmptyList: Story = {
  render: () => (
    <Frame
      path={listPath}
      route={listRoute}
      api={{ ...base, listKnowledgeSources: async () => ({ items: [], total: 0, limit: 50, offset: 0 }) }}
    >
      <KnowledgeSourcesPage />
    </Frame>
  ),
};
export const LoadingList: Story = {
  render: () => (
    <Frame path={listPath} route={listRoute} api={{ ...base, listKnowledgeSources: () => new Promise(() => undefined) }}>
      <KnowledgeSourcesPage />
    </Frame>
  ),
};
export const ErrorList: Story = {
  render: () => (
    <Frame
      path={listPath}
      route={listRoute}
      api={{ ...base, listKnowledgeSources: async () => { throw new AdminApiError('network'); } }}
    >
      <KnowledgeSourcesPage />
    </Frame>
  ),
};
export const DirectTextForm: Story = {
  render: () => <Frame path={`${listPath}/new`} route={createRoute}><KnowledgeSourceCreatePage /></Frame>,
};
export const UrlForm: Story = {
  render: () => <Frame path={`${listPath}/new`} route={createRoute}><KnowledgeSourceCreatePage /></Frame>,
  play: async ({ canvasElement }) => {
    await userEvent.click(await within(canvasElement).findByLabelText('Web page URL'));
  },
};
export const ValidationErrors: Story = {
  render: () => <Frame path={`${listPath}/new`} route={createRoute}><KnowledgeSourceCreatePage /></Frame>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Add knowledge source' }));
    await expect(canvas.getByRole('alert')).toHaveTextContent('Name is required.');
  },
};
export const CompletedDetail: Story = {
  render: () => <Frame path={detailPath} route={detailRoute}><KnowledgeSourceDetailPage /></Frame>,
};
export const QueuedDetail: Story = {
  render: () => (
    <Frame
      path={detailPath}
      route={detailRoute}
      api={{ ...base, getKnowledgeSource: async () => ({ ...source, latestIngestion: { ...source.latestIngestion!, status: 'queued', startedAt: null, completedAt: null } }) }}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
};
export const RunningDetail: Story = {
  render: () => (
    <Frame
      path={detailPath}
      route={detailRoute}
      api={{ ...base, getKnowledgeSource: async () => ({ ...source, latestIngestion: { ...source.latestIngestion!, status: 'running', currentStep: 'embed', completedAt: null } }) }}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
};
export const FailedDetail: Story = {
  render: () => (
    <Frame
      path={detailPath}
      route={detailRoute}
      api={{ ...base, getKnowledgeSource: async () => ({
        ...source,
        latestIngestion: {
          ...source.latestIngestion!,
          status: 'failed',
          currentStep: 'parse',
          failureCode: 'fetch_failed',
          failureMessage: 'The page could not be retrieved.',
        },
      }) }}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
};
export const DisabledDetail: Story = {
  render: () => (
    <Frame path={detailPath} route={detailRoute} api={{ ...base, getKnowledgeSource: async () => ({ ...source, retrievalState: 'disabled' }) }}>
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
};
export const QueuedCreationResult: Story = {
  render: () => (
    <Frame
      path={{ pathname: detailPath, state: { sourceOperation: { sourceId: source.id, outcome: 'queued' } } }}
      route={detailRoute}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('status')).toHaveFocus();
  },
};
export const ReusedCreationResult: Story = {
  render: () => (
    <Frame
      path={{ pathname: detailPath, state: { sourceOperation: { sourceId: source.id, outcome: 'reused' } } }}
      route={detailRoute}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('status')).toHaveFocus();
  },
};
export const ReingestionConfirmation: Story = {
  render: () => <Frame path={detailPath} route={detailRoute}><KnowledgeSourceDetailPage /></Frame>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Re-ingest Policy guide' }));
    await expect(canvas.getByRole('dialog')).toHaveTextContent('Reprocess the persisted source');
  },
};
export const PendingReingestion: Story = {
  render: () => (
    <Frame
      path={detailPath}
      route={detailRoute}
      api={{ ...base, reingestKnowledgeSource: () => new Promise(() => undefined) }}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Re-ingest Policy guide' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm re-ingestion' }));
    await expect(canvas.getByRole('status')).toHaveTextContent('Operation in progress');
    await expect(canvas.getByRole('button', { name: 'Working…' })).toBeDisabled();
  },
};
export const NewReingestionJob: Story = {
  render: () => (
    <Frame path={detailPath} route={detailRoute} api={{ ...base, reingestKnowledgeSource: async () => ({ ...source, activeJobReused: false }) }}>
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Re-ingest Policy guide' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm re-ingestion' }));
    await expect(await canvas.findByRole('status')).toHaveTextContent('Re-ingestion queued.');
  },
};
export const ReusedActiveJob: Story = {
  render: () => <Frame path={detailPath} route={detailRoute}><KnowledgeSourceDetailPage /></Frame>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Re-ingest Policy guide' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm re-ingestion' }));
    await expect(await canvas.findByRole('status')).toHaveTextContent('The active ingestion job was reused.');
  },
};
export const DeleteConfirmation: Story = {
  render: () => <Frame path={detailPath} route={detailRoute}><KnowledgeSourceDetailPage /></Frame>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Delete Policy guide' }));
    await expect(canvas.getByRole('dialog')).toHaveTextContent('owned indexed representation');
  },
};
export const DeleteConflict: Story = {
  render: () => (
    <Frame
      path={detailPath}
      route={detailRoute}
      api={{ ...base, deleteKnowledgeSource: async () => { throw new AdminApiError('conflict', 'active_ingestion'); } }}
    >
      <KnowledgeSourceDetailPage />
    </Frame>
  ),
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Delete Policy guide' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Confirm deletion' }));
    await expect(canvas.getByRole('alert')).toHaveTextContent('ingestion is active');
  },
};
