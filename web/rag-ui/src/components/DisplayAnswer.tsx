import { ShieldCheckIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import SourceId from './SourceId';

const DisplayAnswer = ({
  answer,
  source_ids,
}: {
  answer: string;
  source_ids: string[];
}) => {
  const answerSuccess = answer && source_ids.length > 0;
  return (
    <Section
      title={
        <div className="flex items-center gap-2 mb-3">
          <h2>Answer</h2>
          {answerSuccess && (
            <ShieldCheckIcon className="size-6 text-green-500 stroke-2" />
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-2">
        <p>{answer}</p>
        {source_ids.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="border border-border px-2 py-0.5 rounded-md bg-gray-50">
              Sources: {source_ids.length}
            </span>
            {source_ids.map((id) => (
              <SourceId key={id} id={id} />
            ))}
          </div>
        )}
      </div>
    </Section>
  );
};

export default DisplayAnswer;
