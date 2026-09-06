import type { Meta, StoryObj } from '@storybook/react-vite';
import type { ReactNode } from 'react';
import { createMemoryRouter, Route, RouterProvider, Routes } from 'react-router-dom';
import { expect, fn, userEvent, within } from 'storybook/test';
import { AdminApiError, createAdminApi, type AdminApi, type Assistant } from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import { AssistantFormPage, AssistantsPage, Badge } from './Assistants';

const legalReview: Assistant = {
  id: '11111111-1111-4111-8111-111111111111', slug: 'legal-review', name: 'Legal review',
  status: 'inactive', visibility: 'private', createdAt: '2026-08-01T09:00:00Z',
  updatedAt: '2026-08-04T09:00:00Z', concurrencyToken: '2026-08-04T09:00:00Z',
};
const assistants: Assistant[] = [
  legalReview,
  { ...legalReview, id: '22222222-2222-4222-8222-222222222222', slug: 'customer-support', name: 'Customer support', status: 'active', visibility: 'public', updatedAt: '2026-08-08T13:30:00Z' },
  { ...legalReview, id: '33333333-3333-4333-8333-333333333333', slug: 'people-operations', name: 'People operations', status: 'active', visibility: 'private', updatedAt: '2026-08-06T11:15:00Z' },
  { ...legalReview, id: '44444444-4444-4444-8444-444444444444', slug: 'product-guide', name: 'Product guide', status: 'inactive', visibility: 'public', updatedAt: '2026-08-02T08:45:00Z' },
];
const filteredListAssistants = fn(async (options: Parameters<AdminApi['listAssistants']>[0] = {}) => {
  const items = assistants.filter((assistant) => (!options.status || assistant.status === options.status) && (!options.visibility || assistant.visibility === options.visibility));
  return { items, total: items.length, limit: 50, offset: 0 };
});

function apiWith(overrides: Partial<AdminApi> = {}): AdminApi {
  return {
    ...createAdminApi(''),
    currentUser: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
    login: async () => ({ id: 'admin', email: 'admin@example.test', role: 'administrator' }),
    logout: async () => undefined,
    listAssistants: async () => ({ items: assistants, total: 4, limit: 50, offset: 0 }),
    getAssistant: async () => ({ ...legalReview, knowledgeSourceCount: 0, deletionAllowed: true }),
    createAssistant: async () => legalReview,
    updateAssistant: async () => legalReview,
    deleteAssistant: async () => undefined,
    ...overrides,
  };
}

function Frame({ api = apiWith(), path = '/admin/assistants', children }: { api?: AdminApi; path?: string; children: ReactNode }) {
  const router = createMemoryRouter([{ path: '*', element: <AuthProvider api={api} initialUser={{ id: 'admin', email: 'admin@example.test', role: 'administrator' }}>{children}</AuthProvider> }], { initialEntries: [path] });
  return <RouterProvider router={router} />;
}

const meta = { title: 'Assistants/Management' } satisfies Meta;
export default meta;
type Story = StoryObj;

export const PopulatedList: Story = { render: () => <Frame><AssistantsPage /></Frame> };
export const FilteredList: Story = {
  render: () => <Frame api={apiWith({ listAssistants: filteredListAssistants })}><AssistantsPage /></Frame>,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    filteredListAssistants.mockClear();
    await userEvent.selectOptions(await canvas.findByLabelText('Status'), 'active');
    await userEvent.selectOptions(await canvas.findByLabelText('Visibility'), 'public');
    await expect(canvas.findByRole('button', { name: 'Actions for Customer support' })).resolves.toBeVisible();
    await expect(canvas.queryByRole('button', { name: 'Actions for Legal review' })).not.toBeInTheDocument();
    await expect(filteredListAssistants).toHaveBeenLastCalledWith(
      { limit: 50, offset: 0, status: 'active', visibility: 'public' },
      expect.any(AbortSignal),
    );
  },
};
export const EmptyList: Story = { render: () => <Frame api={apiWith({ listAssistants: async () => ({ items: [], total: 0, limit: 50, offset: 0 }) })}><AssistantsPage /></Frame> };
export const LoadingList: Story = { render: () => <Frame api={apiWith({ listAssistants: () => new Promise(() => undefined) })}><AssistantsPage /></Frame> };
export const ErrorList: Story = { render: () => <Frame api={apiWith({ listAssistants: async () => { throw new AdminApiError('network'); } })}><AssistantsPage /></Frame> };
export const NarrowList: Story = {
  parameters: { viewport: { defaultViewport: 'mobile1' } },
  render: () => <div className="stories-mobile"><Frame><AssistantsPage /></Frame></div>,
};

export const CreateForm: Story = { render: () => <Frame path="/admin/assistants/new"><AssistantFormPage mode="create" /></Frame> };
export const EditForm: Story = { render: () => <Frame path={`/admin/assistants/${legalReview.id}/edit`}><Routes><Route path="/admin/assistants/:assistantId/edit" element={<AssistantFormPage mode="edit" />} /></Routes></Frame> };
export const ValidationErrors: Story = {
  render: () => <Frame path="/admin/assistants/new"><AssistantFormPage mode="create" /></Frame>,
  play: async ({ canvasElement }) => { const canvas = within(canvasElement); await userEvent.click(await canvas.findByRole('button', { name: 'Save assistant' })); await expect(canvas.getByRole('alert')).toHaveTextContent('Name is required.'); },
};
export const DeleteConfirmation: Story = {
  render: () => <Frame><AssistantsPage /></Frame>,
  play: async ({ canvasElement }) => { const canvas = within(canvasElement); await userEvent.click(await canvas.findByRole('button', { name: 'Actions for Legal review' })); await userEvent.click(canvas.getByRole('menuitem', { name: /Delete/ })); await expect(canvas.getByRole('dialog')).toHaveTextContent('Delete Legal review?'); },
};
export const PendingStatusAction: Story = {
  render: () => <Frame api={apiWith({ updateAssistant: () => new Promise(() => undefined) })}><AssistantsPage /></Frame>,
  play: async ({ canvasElement }) => { const canvas = within(canvasElement); await userEvent.click(await canvas.findByRole('button', { name: 'Actions for Legal review' })); await userEvent.click(canvas.getByRole('menuitem', { name: /Activate/ })); await userEvent.click(canvas.getByRole('button', { name: 'Confirm' })); await expect(canvas.getByRole('button', { name: 'Working…' })).toBeDisabled(); },
};
export const StatusBadges: Story = { render: () => <div className="actions"><Badge value="active" /><Badge value="inactive" /><Badge value="public" /><Badge value="private" /></div> };
