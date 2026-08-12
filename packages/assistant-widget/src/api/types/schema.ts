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
  '/assistant/knowledge/ingestions': {
    post: {
      requestBody: {
        content: {
          'application/json': components['schemas']['StartIngestionRequest']
        }
      }
      responses: {
        201: {
          content: {
            'application/json': components['schemas']['IngestionJobResponse']
          }
        }
      }
    }
  }
  '/assistant/knowledge/ingestions/{jobId}': {
    get: {
      parameters: {
        path: {
          jobId: string
        }
      }
      responses: {
        200: {
          content: {
            'application/json': components['schemas']['IngestionJobResponse']
          }
        }
        404: {
          content: {
            'application/json': components['schemas']['ErrorResponse']
          }
        }
      }
    }
  }
  '/assistant/knowledge/status': {
    get: {
      responses: {
        200: {
          content: {
            'application/json': components['schemas']['KnowledgeStatusResponse']
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
    ErrorResponse: {
      detail: string
    }
    IngestionJobResponse: {
      jobId: string
      status: 'pending' | 'running' | 'completed' | 'failed'
      sourceUrl: string
      documentsDiscovered: number
      documentsProcessed: number
      chunksCreated: number
      error: string | null
      createdAt: string
      startedAt: string | null
      completedAt: string | null
    }
    KnowledgeStatusResponse: {
      documents: number
      chunks: number
      lastIngestionAt: string | null
      lastIngestionStatus: 'pending' | 'running' | 'completed' | 'failed' | null
    }
    SourceReference: {
      id: string
      title: string
    }
    StartIngestionRequest: {
      url: string
    }
  }
}
