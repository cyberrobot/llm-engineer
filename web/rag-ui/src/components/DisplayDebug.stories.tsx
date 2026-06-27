import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import type { DebugInstance } from '../App';
import { DebugProvider } from './DebugContext';
import DisplayDebug from './DisplayDebug';

const DEBUG_SECTION_COLLAPSED_KEY = 'rag-ui.debug-section-collapsed';

const debugFixture: DebugInstance = {
  id: 'debug-story-001',
  timestamp: '2026-06-27T09:30:00Z',
  user_role: 'Compliance reviewer',
  question:
    'What checks are required before approving a large international payment?',
  reply: {
    answer:
      'Confirm the approval threshold, verify sanctions screening, and record the dual authorization outcome.',
    source_ids: ['policy-payments-001', 'policy-risk-004'],
  },
  metrics: {
    retrieval_time: 0.42,
    llm_time: 1.16,
    total_time: 1.58,
    cache_hit: false,
    input_tokens: 312,
    output_tokens: 96,
  },
  queries: [
    'large international payment approval checks',
    'dual authorization sanctions screening payment policy',
  ],
  retrieved_chunks: [
    {
      rank: 1,
      id: 'chunk-001',
      doc_id: 'policy-payments-001',
      distance: 0.11,
      hybrid_score: 0.92,
      text_snippet:
        'Large international payments require dual authorization and sanctions screening before release.',
      keyword_match: 4,
    },
    {
      rank: 2,
      id: 'chunk-002',
      doc_id: 'policy-risk-004',
      distance: 0.2,
      hybrid_score: 0.84,
      text_snippet:
        'Reviewers must record approval rationale and any risk exceptions before payment execution.',
      keyword_match: 3,
    },
  ],
  reranked_chunks: [
    {
      rank: 1,
      id: 'chunk-001',
      doc_id: 'policy-payments-001',
      distance: 0.11,
      hybrid_score: 0.92,
      text_snippet:
        'Large international payments require dual authorization and sanctions screening before release.',
      keyword_match: 4,
    },
  ],
};

const mockAuditLogFetch = () => {
  window.fetch = async () =>
    new Response(JSON.stringify([debugFixture]), {
      headers: {
        'Content-Type': 'application/json',
      },
      status: 200,
    });
};

const meta = {
  title: 'Components/DisplayDebug',
  component: DisplayDebug,
  decorators: [
    (Story, context) => {
      mockAuditLogFetch();

      if (typeof context.parameters.debugCollapsed === 'boolean') {
        localStorage.setItem(
          DEBUG_SECTION_COLLAPSED_KEY,
          JSON.stringify(context.parameters.debugCollapsed),
        );
      } else {
        localStorage.removeItem(DEBUG_SECTION_COLLAPSED_KEY);
      }

      return (
        <DebugProvider>
          <div className="max-w-5xl p-5">
            <Story />
          </div>
        </DebugProvider>
      );
    },
  ],
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof DisplayDebug>;

export default meta;

type Story = StoryObj<typeof meta>;

export const CollapsedByDefault: Story = {
  parameters: {
    debugCollapsed: undefined,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const expandButton = canvas.getByLabelText('Expand debug section');
    const content = canvasElement.querySelector('#debug-section-content');

    await expect(expandButton).toBeVisible();
    await expect(expandButton).toHaveAttribute('aria-expanded', 'false');
    await expect(content).toHaveAttribute('aria-hidden', 'true');
    await expect(
      canvas.getByText('Retrieval & Generation Debug').parentElement,
    ).toHaveClass('opacity-0');
  },
};

export const Expanded: Story = {
  parameters: {
    debugCollapsed: false,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByLabelText('Collapse debug section')).toBeVisible();
    await expect(
      await canvas.findByText('Retrieval & Generation Debug'),
    ).toBeVisible();
    await waitFor(() => {
      expect(canvas.getAllByText(debugFixture.question)).toHaveLength(2);
    });
  },
};

export const ToggleInteraction: Story = {
  parameters: {
    debugCollapsed: true,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const expandButton = canvas.getByLabelText('Expand debug section');

    await userEvent.click(expandButton);

    await waitFor(() => {
      expect(canvas.getByLabelText('Collapse debug section')).toBeVisible();
    });
    await waitFor(() => {
      expect(canvas.getAllByText(debugFixture.question)).toHaveLength(2);
    });
  },
};
