import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import App from './App';
import AuthenticatedRagBoundary from './components/AuthenticatedRagBoundary';
import { DebugProvider } from './components/DebugContext';
import UserProvider from './components/UserProvider';

type CapturedRequest = {
  url: string;
  init?: RequestInit;
};

let capturedRequests: CapturedRequest[] = [];

const successfulRagResponse = {
  reply: { answer: 'Role-scoped answer', source_ids: [] },
  sources: [],
  evaluation: null,
};

const AuthenticatedRagExperience = () => (
  <AuthenticatedRagBoundary>
    <DebugProvider>
      <UserProvider>
        <App />
      </UserProvider>
    </DebugProvider>
  </AuthenticatedRagBoundary>
);

const meta = {
  title: 'RAG UI/Authenticated experience',
  component: AuthenticatedRagExperience,
  decorators: [
    (Story) => {
      capturedRequests = [];
      window.fetch = async (input, init) => {
        const url = String(input);
        capturedRequests.push({ url, init });

        if (url.endsWith('/admin/auth/me')) {
          return new Response(
            JSON.stringify({ user: { id: 'admin-1', role: 'administrator' } }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
        }
        if (url.endsWith('/audit-logs')) {
          return new Response('[]', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify(successfulRagResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      };
      return <Story />;
    },
  ],
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof AuthenticatedRagExperience>;

export default meta;
type Story = StoryObj<typeof meta>;

export const RoleSelectionControlsRagHint: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const roleSelector = await canvas.findByLabelText('Select User Role');
    const input = canvas.getByPlaceholderText('Ask something...');

    await expect(roleSelector).toHaveTextContent('Doctor');
    await userEvent.type(input, 'doctor question');
    await userEvent.click(canvas.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(ragRequests()).toHaveLength(1);
    });
    expectRequestRole(ragRequests()[0], 'doctor');

    await userEvent.click(roleSelector);
    for (const role of ['Doctor', 'Nurse', 'Analyst', 'Manager', 'Agent']) {
      await expect(canvas.getByLabelText(`Select ${role}`)).toBeVisible();
    }
    await userEvent.click(canvas.getByLabelText('Select Manager'));
    await expect(roleSelector).toHaveTextContent('Manager');
    await userEvent.clear(input);
    await userEvent.type(input, 'manager question');
    await userEvent.click(canvas.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(ragRequests()).toHaveLength(2);
    });
    expectRequestRole(ragRequests()[1], 'manager');
  },
};

function ragRequests() {
  return capturedRequests.filter(({ url }) => url.endsWith('/rag-chat'));
}

function expectRequestRole(request: CapturedRequest, expectedRole: string) {
  expect(request.init?.credentials).toBe('include');
  expect(JSON.parse(String(request.init?.body))).toMatchObject({
    user_role: expectedRole,
  });
}
