import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayDebugSummary from './DisplayDebugSummary';
import DisplayGeneratedQueries from './DisplayGeneratedQueries';
import DisplayRetrievedChunks from './DisplayRetrievedChunks';

type DebugProps = {
  id: string;
  timestamp: string;
  user_role: string;
  metrics: Metrics;
  queries: string[];
  retrieved_chunks: RetrievedChunk[];
};

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

const DisplayDebug = ({ debug }: { debug: DebugProps }) => {
  return (
    <Section
      title={
        <div className="flex items-center gap-2 mb-3">
          <CodeBracketIcon className="size-6 text-accent-bg stroke-2" />
          <h2>Retrieval & Generation Debug</h2>
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        <DisplayDebugSummary
          id={debug.id}
          timestamp={debug.timestamp}
          userRole={debug.user_role}
          queries={debug.queries.length}
          retrievedChunks={debug.retrieved_chunks.length}
          metrics={debug.metrics}
        />
        <DisplayGeneratedQueries items={debug.queries} />
        <DisplayRetrievedChunks chunks={debug.retrieved_chunks} />
      </div>
    </Section>
  );
};

export default DisplayDebug;
