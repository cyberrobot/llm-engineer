import type { Meta, StoryObj } from '@storybook/react-vite';
import { MemoryRouter } from 'react-router-dom';
import { AdminApiError, type AdminApi, type OperationsSummary } from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import { DashboardPage } from './Dashboard';

const summary: OperationsSummary = {
  generatedAt: '2026-08-25T10:00:00Z',
  health: 'healthy',
  maintenance: false,
  cache: { regions: 3 },
  jobs: { running: 1, failed: 0 },
  audit: { today: 4 },
  assistants: { total: 12, published: 8 },
  knowledgeSources: { total: 24, enabled: 21, failed: null },
  ingestion: { queued: 2, running: 1, recoverable: 0, failed: 0, oldestQueuedAgeSeconds: 4320, workersObserved: 2 },
};

function apiWith(getOperationsSummary: AdminApi['getOperationsSummary']): AdminApi {
  const unsupported = async () => { throw new AdminApiError('invalid_request'); };
  return {
    currentUser: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
    login: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
    logout: async () => undefined,
    getOperationsSummary,
    listAssistants: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    getAssistant: unsupported,
    createAssistant: unsupported,
    updateAssistant: unsupported,
    deleteAssistant: unsupported,
    getAssistantBehaviour: unsupported,
    updateAssistantBehaviour: unsupported,
    publishAssistantBehaviour: unsupported,
    previewAssistantMessage: unsupported,
    listKnowledgeSources: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    getKnowledgeSource: unsupported,
    createKnowledgeSource: unsupported,
    updateKnowledgeSourceRetrieval: unsupported,
    reingestKnowledgeSource: unsupported,
    deleteKnowledgeSource: unsupported,
  };
}

function Frame({ api }: { api: AdminApi }) {
  return (
    <MemoryRouter>
      <AuthProvider api={api} initialUser={{ id: 'admin', email: 'admin@example.test', role: 'administrator' }}>
        <DashboardPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

const meta = { title: 'Dashboard/Operational summary', component: DashboardPage } satisfies Meta<typeof DashboardPage>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Healthy: Story = { render: () => <Frame api={apiWith(async () => summary)} /> };
export const AttentionRequired: Story = {
  render: () => <Frame api={apiWith(async () => ({
    ...summary,
    health: 'degraded',
    maintenance: true,
    jobs: { running: 0, failed: 2 },
    knowledgeSources: { total: 24, enabled: 20, failed: 1 },
    ingestion: { queued: 3, running: 0, recoverable: 1, failed: 2, oldestQueuedAgeSeconds: 7320, workersObserved: 0 },
  }))} />,
};
export const ZeroState: Story = {
  render: () => <Frame api={apiWith(async () => ({
    ...summary,
    cache: { regions: 0 }, jobs: { running: 0, failed: 0 }, audit: { today: 0 },
    assistants: { total: 0, published: 0 }, knowledgeSources: { total: 0, enabled: 0, failed: 0 },
    ingestion: { queued: 0, running: 0, recoverable: 0, failed: 0, oldestQueuedAgeSeconds: 0, workersObserved: 0 },
  }))} />,
};
export const Loading: Story = { render: () => <Frame api={apiWith(() => new Promise(() => undefined))} /> };
export const ReadFailure: Story = { render: () => <Frame api={apiWith(async () => { throw new AdminApiError('network'); })} /> };
