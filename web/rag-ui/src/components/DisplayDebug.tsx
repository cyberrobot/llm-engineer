import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayDebugSummary, {
  DisplayDebugSummarySkeleton,
} from './DisplayDebugSummary';
import DisplayGeneratedQueries, {
  DisplayGeneratedQueriesSkeleton,
} from './DisplayGeneratedQueries';
import DisplayRetrievedChunks, {
  DisplayRetrievedChunksSkeleton,
} from './DisplayRetrievedChunks';
import DisplayDebugHistory from './DisplayDebugHistory';
import { useDebugContext } from './DebugContext';
import DisplayDebugQuestion, {
  DisplayDebugQuestionSkeleton,
} from './DisplayDebugQuestion';

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
          <CodeBracketIcon className="size-5 text-accent-bg stroke-2" />
          <h2>Retrieval & Generation Debug</h2>
        </div>
      }
    >
      <div className="flex gap-5 lg:flex-row flex-col justify-between">
        <div className="flex flex-col gap-5">
          {loading ? (
            <>
              <DisplayDebugSummarySkeleton />
              <DisplayDebugQuestionSkeleton />
              <DisplayGeneratedQueriesSkeleton />
              <DisplayRetrievedChunksSkeleton />
            </>
          ) : latestDebug ? (
            <>
              <DisplayDebugSummary
                id={latestDebug.id}
                timestamp={latestDebug.timestamp}
                userRole={latestDebug.user_role}
                queries={latestDebug.queries.length}
                retrievedChunks={latestDebug.retrieved_chunks.length}
                metrics={latestDebug.metrics}
              />
              <DisplayDebugQuestion question={latestDebug.question} />
              <DisplayGeneratedQueries items={latestDebug.queries} />
              <DisplayRetrievedChunks chunks={latestDebug.retrieved_chunks} />
            </>
          ) : (
            <p>No debug data available.</p>
          )}
        </div>
        <div className="lg:w-70 min-w-[280px] w-full">
          <DisplayDebugHistory />
        </div>
      </div>
    </Section>
  );
};

export default DisplayDebug;
