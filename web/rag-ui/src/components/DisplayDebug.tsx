import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayDebugSummary from './DisplayDebugSummary';
import DisplayGeneratedQueries from './DisplayGeneratedQueries';
import DisplayRetrievedChunks from './DisplayRetrievedChunks';
import DisplayDebugHistory from './DisplayDebugHistory';
import { useDebugContext } from './DebugContext';

export type Metrics = {
  retrieval_time: number;
  llm_time: number;
  total_time: number;
  cache_hit: boolean;
  input_tokens: number;
  output_tokens: number;
};

export type RetrievedChunk = {
  rank: number;
  id: string;
  doc_id: string;
  distance: number;
  hybrid_score: number;
  text_snippet: string;
  keyword_match: number;
};

const DisplayDebug = () => {
  const { latestDebug, loading } = useDebugContext();

  return (
    <Section
      title={
        <div className="flex items-center gap-2 mb-3">
          <CodeBracketIcon className="size-6 text-accent-bg stroke-2" />
          <h2>Retrieval & Generation Debug</h2>
        </div>
      }
    >
      <div className="flex gap-5">
        {latestDebug && (
          <div className="flex flex-col gap-5 w-3/4">
            <DisplayDebugSummary
              id={latestDebug.id}
              timestamp={latestDebug.timestamp}
              userRole={latestDebug.user_role}
              queries={latestDebug.queries.length}
              retrievedChunks={latestDebug.retrieved_chunks.length}
              metrics={latestDebug.metrics}
              loading={loading}
            />
            <DisplayGeneratedQueries
              items={latestDebug.queries}
              loading={loading}
            />
            <DisplayRetrievedChunks
              chunks={latestDebug.retrieved_chunks}
              loading={loading}
            />
          </div>
        )}
        <div className="w-1/4 min-w-[60px]">
          <DisplayDebugHistory />
        </div>
      </div>
    </Section>
  );
};

export default DisplayDebug;
