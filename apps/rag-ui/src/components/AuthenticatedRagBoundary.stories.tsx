import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, within } from 'storybook/test';
import AuthenticatedRagBoundary from './AuthenticatedRagBoundary';

let lastRequestInit: RequestInit | undefined;

const meta = {
  title: 'Components/AuthenticatedRagBoundary',
  component: AuthenticatedRagBoundary,
  args: {
    children: <div>Protected RAG content</div>,
  },
  decorators: [
    (Story, context) => {
      window.fetch = async (_input, init) => {
        lastRequestInit = init;
        const authenticated = context.parameters.authenticated !== false;
        return new Response(
          JSON.stringify(
            authenticated
              ? { user: { id: 'admin-1', role: 'administrator' } }
              : { detail: 'fictional sensitive authentication detail' },
          ),
          {
            status: authenticated ? 200 : 401,
            headers: { 'Content-Type': 'application/json' },
          },
        );
      };
      return <Story />;
    },
  ],
} satisfies Meta<typeof AuthenticatedRagBoundary>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Authenticated: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(await canvas.findByText('Protected RAG content')).toBeVisible();
    await expect(lastRequestInit?.credentials).toBe('include');
  },
};

export const Unauthenticated: Story = {
  parameters: { authenticated: false },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(
      await canvas.findByText('Administrator authentication required'),
    ).toBeVisible();
    await expect(
      canvas.queryByText('fictional sensitive authentication detail'),
    ).not.toBeInTheDocument();
    await expect(canvas.queryByText('Protected RAG content')).not.toBeInTheDocument();
  },
};
