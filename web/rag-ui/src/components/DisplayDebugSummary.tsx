import { cacheBooleanToString } from '../utils/display';
import { formatDuration, localStringFromUTC } from '../utils/time';
import type { Metrics } from './DisplayDebug';
import SkeletonBlock from './SkeletonBlock';

const DisplayDebugSummary = ({
  metrics,
  id,
  timestamp,
  userRole,
  queries,
  retrievedChunks,
  loading,
}: {
  id: string;
  timestamp: string;
  userRole: string;
  queries: number;
  retrievedChunks: number;
  metrics: Metrics;
  loading?: boolean;
}) => {
  const localDateFromUtc = localStringFromUTC(timestamp);
  return (
    <div className="grid grid-cols-3 lg:grid-cols-5 gap-3">
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
          className="flex flex-col gap-0.5 border border-border p-2 rounded bg-gray-50"
        >
          <span className="text-text font-semibold">{item.title}</span>
          {loading ? (
            <SkeletonBlock height="1.5rem" />
          ) : (
            <span className="font-bold">{item.value}</span>
          )}
        </div>
      ))}
    </div>
  );
};

export default DisplayDebugSummary;
