import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayMetrics from './DisplayMetrics';
import DisplayGeneratedQueries from './DisplayGeneratedQueries';
import DisplayRetrievedChunks from './DisplayRetrievedChunks';

type DebugProps = {
  id: string;
  metrics: Metrics;
  multi_query: string[];
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
        <DisplayMetrics metrics={debug.metrics} id={debug.id} />
        <DisplayGeneratedQueries items={debug.multi_query} />
        <DisplayRetrievedChunks chunks={debug.retrieved_chunks} />
      </div>
    </Section>
  );
};

export default DisplayDebug;
