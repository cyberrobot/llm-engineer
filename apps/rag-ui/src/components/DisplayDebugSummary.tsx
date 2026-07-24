import { cacheBooleanToString } from '../utils/display';
import { formatDuration, localStringFromUTC } from '../utils/time';
import type { Metrics } from './DisplayDebug';
import SkeletonBlock from './SkeletonBlock';

const wrapperClasses =
  'grid w-full min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4';

const DisplayDebugSummary = ({
  metrics,
  id,
  timestamp,
  userRole,
  queries,
  retrievedChunks,
}: {
  id: string;
  timestamp: string;
  userRole: string;
  queries: number;
  retrievedChunks: number;
  metrics: Metrics;
}) => {
  const localDateFromUtc = localStringFromUTC(timestamp);
  return (
    <div className={wrapperClasses}>
      {[
        { title: 'Query ID', value: id },
        {
          title: 'Timestamp',
          value: localDateFromUtc,
        },
        {
          title: 'User Role',
          value: userRole,
        },
        {
          title: 'Cache',
          value: cacheBooleanToString(metrics.cache_hit),
        },
        {
          title: 'Queries',
          value: queries,
        },
        {
          title: 'Retrieved Chunks',
          value: retrievedChunks,
        },
        {
          title: 'Retrieval Time',
          value: formatDuration(metrics.retrieval_time),
        },
        { title: 'LLM Time', value: formatDuration(metrics.llm_time) },
        { title: 'Total Time', value: formatDuration(metrics.total_time) },
        { title: 'Input Tokens', value: metrics.input_tokens },
        { title: 'Output Tokens', value: metrics.output_tokens },
      ].map((item, index) => (
        <div
          key={index}
          className="flex min-w-0 flex-col gap-0.5 border border-border p-2 rounded bg-gray-50"
        >
          <span className="text-text font-semibold">{item.title}</span>
          <span className="break-words font-bold">{item.value}</span>
        </div>
      ))}
    </div>
  );
};

export default DisplayDebugSummary;

export const DisplayDebugSummarySkeleton = () => {
  return (
    <div className={wrapperClasses}>
      {[...Array(11)].map((_, index) => (
        <div
          key={index}
          className="flex min-w-0 flex-col gap-0.5 border border-border p-2 rounded bg-gray-50"
        >
          <span className="text-text font-semibold">
            <SkeletonBlock height="1.5rem" width="90px" />
          </span>
          <span className="font-bold">
            <SkeletonBlock height="1.5rem" width="90px" />
          </span>
        </div>
      ))}
    </div>
  );
};
