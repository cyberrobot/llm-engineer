import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayMetrics, { type Metrics } from './DisplayMetrics';
import DisplayGeneratedQueries from './DisplayGeneratedQueries';

type DebugProps = {
  id: string;
  metrics: Metrics;
  multi_query: string[];
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
      </div>
    </Section>
  );
};

export default DisplayDebug;
