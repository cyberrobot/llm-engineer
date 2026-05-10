import { ShieldCheckIcon } from '@heroicons/react/24/outline';

const DisplayAnswer = ({
  answer,
  source_ids,
}: {
  answer: string;
  source_ids: string[];
}) => {
  const answerSuccess = answer && source_ids.length > 0;
  return (
    <div className="section border border-border rounded p-4">
      <div className="flex items-center gap-2 mb-2">
        <h2>Answer</h2>
        {answerSuccess && (
          <ShieldCheckIcon className="w-5 h-5 text-green-500" />
        )}
      </div>
      <div className="flex flex-col gap-1">
        <p>{answer}</p>
        {source_ids.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="border border-border px-2 py-0.5 rounded-md bg-gray-100 text-sm">
              Sources: {source_ids.length}
            </span>
            {source_ids.map((id) => (
              <span
                key={id}
                className="border border-secondary px-2 py-0.5 rounded-md bg-secondary-bg text-secondary text-sm"
              >
                {id}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DisplayAnswer;
