import { describe, expect, it } from 'vitest'

import { readAssistantWidgetDemoConfig } from './assistantWidgetDemoConfig'

describe('assistant widget demo configuration', () => {
  it('reads, trims, and normalizes valid public environment values', () => {
    expect(
      readAssistantWidgetDemoConfig({
        VITE_ASSISTANT_API_BASE_URL: '  http://localhost:8000///  ',
        VITE_ASSISTANT_ID: '  redmoor  ',
      }),
    ).toEqual({
      ok: true,
      config: {
        apiBaseUrl: 'http://localhost:8000',
        assistantId: 'redmoor',
      },
    })
  })

  it.each([
    [
      { VITE_ASSISTANT_ID: 'redmoor' },
      ['VITE_ASSISTANT_API_BASE_URL'],
    ],
    [
      { VITE_ASSISTANT_API_BASE_URL: 'http://localhost:8000', VITE_ASSISTANT_ID: '   ' },
      ['VITE_ASSISTANT_ID'],
    ],
    [
      {},
      ['VITE_ASSISTANT_API_BASE_URL', 'VITE_ASSISTANT_ID'],
    ],
  ])('reports missing required values without supplying defaults', (environment, variables) => {
    expect(readAssistantWidgetDemoConfig(environment)).toEqual({
      ok: false,
      variables,
      reason: 'missing',
    })
  })

  it.each(['localhost:8000', 'ftp://localhost:8000', 'https://user@example.test'])(
    'rejects the malformed or unsupported API base URL %s',
    (apiBaseUrl) => {
      expect(
        readAssistantWidgetDemoConfig({
          VITE_ASSISTANT_API_BASE_URL: apiBaseUrl,
          VITE_ASSISTANT_ID: 'redmoor',
        }),
      ).toEqual({
        ok: false,
        variables: ['VITE_ASSISTANT_API_BASE_URL'],
        reason: 'invalid',
      })
    },
  )

  it('rejects an assistant identifier that does not match the backend slug contract', () => {
    expect(
      readAssistantWidgetDemoConfig({
        VITE_ASSISTANT_API_BASE_URL: 'http://localhost:8000',
        VITE_ASSISTANT_ID: 'Redmoor Assistant',
      }),
    ).toEqual({
      ok: false,
      variables: ['VITE_ASSISTANT_ID'],
      reason: 'invalid',
    })
  })
})
