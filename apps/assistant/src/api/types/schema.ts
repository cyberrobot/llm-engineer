/**
 * Generated from the backend OpenAPI contract.
 * Do not edit request or response shapes by hand.
 */
export interface paths {
  '/assistant/chat': {
    post: {
      requestBody: {
        content: {
          'application/json': components['schemas']['ChatRequest']
        }
      }
      responses: {
        200: {
          content: {
            'application/json': components['schemas']['ChatResponse']
          }
        }
      }
    }
  }
}

export interface components {
  schemas: {
    ChatRequest: {
      message: string
    }
    ChatResponse: {
      message: string
      sources?: components['schemas']['SourceReference'][]
    }
    SourceReference: {
      id: string
      title: string
    }
  }
}
