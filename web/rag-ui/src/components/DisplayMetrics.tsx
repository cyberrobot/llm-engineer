import { formatDuration } from '../utils/time';

type Metrics = {
  retrieval_time: number;
  llm_time: number;
  total_time: number;
  cache_hit: boolean;
  input_tokens: number;
  output_tokens: number;
};

const DisplayMetrics = ({ metrics, id }: { metrics: Metrics; id: string }) => {
  return (
    <div className="grid grid-cols-1 md:grid- lg:grid-cols-4 gap-3">
      {[
        { title: 'Query ID', value: id },
        {
          title: 'Retrieval Time',
          value: formatDuration(metrics.retrieval_time),
        },
        { title: 'LLM Time', value: formatDuration(metrics.llm_time) },
        { title: 'Total Time', value: formatDuration(metrics.total_time) },
        {
          title: 'Cache',
          value: metrics.cache_hit ? (
            <span className="text-green-500">HIT</span>
          ) : (
            <span className="text-red-500">MISS</span>
          ),
        },
        { title: 'Input Tokens', value: metrics.input_tokens },
        { title: 'Output Tokens', value: metrics.output_tokens },
      ].map((item, index) => (
        <div
          key={index}
          className="flex flex-col gap-0.5 border border-border p-2 rounded bg-gray-50"
        >
          <span className="text-sm">{item.title}</span>
          <span className="text-sm font-bold">{item.value}</span>
        </div>
      ))}
    </div>
  );
};

export default DisplayMetrics;
