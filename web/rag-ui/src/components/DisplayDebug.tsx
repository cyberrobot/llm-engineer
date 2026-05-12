import { CodeBracketIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayMetrics from './DisplayMetrics';

const DisplayDebug = ({ debug }: { debug: any }) => {
  return (
    <Section
      title={
        <div className="flex items-center gap-2 mb-3">
          <CodeBracketIcon className="size-6 text-accent-bg stroke-2" />
          <h2>Retrieval & Generation Debug</h2>
        </div>
      }
    >
      <DisplayMetrics metrics={debug.metrics} id={debug.id} />
    </Section>
  );
};

export default DisplayDebug;
