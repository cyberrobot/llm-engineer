import {
  AdjustmentsHorizontalIcon,
  CodeBracketIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import useLocalStorageState from 'use-local-storage-state';
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
import DisplayRerankedChunks, {
  DisplayRerankedChunksSkeleton,
} from './DisplayRerankedChunks';

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

export type RerankedChunk = {
  rank: number;
  id: string;
  doc_id: string;
  distance: number;
  hybrid_score: number;
  text_snippet: string;
  keyword_match: number;
};

const DEBUG_SECTION_COLLAPSED_KEY = 'rag-ui.debug-section-collapsed';

const DisplayDebug = () => {
  const { latestDebug, loading } = useDebugContext();
  const [isCollapsed, setIsCollapsed] = useLocalStorageState(
    DEBUG_SECTION_COLLAPSED_KEY,
    {
      defaultValue: true,
    },
  );

  return (
    <Section
      className={`relative overflow-hidden transition-all duration-300 ease-out ${
        isCollapsed ? 'border-0' : ''
      }`}
      title={
        <>
          <div
            className={`mb-3 mr-12 flex items-center gap-2 transition-opacity ease-out ${
              isCollapsed
                ? 'pointer-events-none opacity-0 duration-200'
                : 'opacity-100 duration-300'
            }`}
          >
            <CodeBracketIcon className="size-5 text-accent-bg stroke-2" />
            <h2>Retrieval & Generation Debug</h2>
          </div>
          <button
            type="button"
            aria-expanded={!isCollapsed}
            aria-controls="debug-section-content"
            aria-label={
              isCollapsed ? 'Expand debug section' : 'Collapse debug section'
            }
            onClick={() => setIsCollapsed((collapsed) => !collapsed)}
            className="absolute top-3 right-4 z-1 flex size-9 cursor-pointer items-center justify-center rounded border border-border bg-white text-text transition-colors hover:bg-gray-50 hover:text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary"
          >
            {isCollapsed ? (
              <AdjustmentsHorizontalIcon className="size-5 stroke-2" />
            ) : (
              <XMarkIcon className="size-5 stroke-2" />
            )}
          </button>
        </>
      }
    >
      <div
        id="debug-section-content"
        aria-hidden={isCollapsed}
        inert={isCollapsed ? true : undefined}
        className={`grid transition-[grid-template-rows,opacity] ease-out ${
          isCollapsed
            ? 'grid-rows-[0fr] opacity-0 duration-200'
            : 'grid-rows-[1fr] opacity-100 duration-300'
        }`}
      >
        <div className="min-h-0 overflow-hidden">
          <div className="flex w-full flex-col gap-5 lg:flex-row">
            <div className="flex min-w-0 w-full flex-1 flex-col gap-5">
              {loading ? (
                <>
                  <DisplayDebugSummarySkeleton />
                  <DisplayDebugQuestionSkeleton />
                  <DisplayGeneratedQueriesSkeleton />
                  <DisplayRetrievedChunksSkeleton />
                  <DisplayRerankedChunksSkeleton />
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
                  <DisplayRetrievedChunks
                    chunks={latestDebug.retrieved_chunks}
                  />
                  <DisplayRerankedChunks chunks={latestDebug.reranked_chunks} />
                </>
              ) : (
                <p>No debug data available.</p>
              )}
            </div>
            <div className="w-full shrink-0 lg:w-70 lg:min-w-[280px]">
              <DisplayDebugHistory />
            </div>
          </div>
        </div>
      </div>
    </Section>
  );
};

export default DisplayDebug;
