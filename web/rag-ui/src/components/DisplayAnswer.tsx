import { ShieldCheckIcon } from '@heroicons/react/24/outline';
import Section from './Section';
import DisplayAnswerSkeleton from './DisplayAnswerSkeleton';
import AnswerEvaluationCards from './AnswerEvaluationCards';

export type EvaluationMetrics = {
  groundedness_score: number;
  verified_sentences: number;
  total_sentences: number;
  citation_count: number;
};

interface DisplayAnswerProps {
  answer?: string;
  source_ids?: string[];
  evaluationMetrics?: EvaluationMetrics;
  loading?: boolean;
}

const DisplayAnswer = ({
  answer,
  source_ids,
  evaluationMetrics,
  loading = false,
}: DisplayAnswerProps) => {
  if (!answer && !loading) {
    return null;
  }

  const answerSuccess = answer && source_ids && source_ids.length > 0;

  return (
    <Section
      title={
        <div className="flex items-center gap-2 mb-3">
          <h2>Answer</h2>
          {answerSuccess && !loading && (
            <ShieldCheckIcon className="size-6 text-green-500 stroke-2" />
          )}
        </div>
      }
    >
      {loading ? (
        <DisplayAnswerSkeleton />
      ) : (
        <div className="flex flex-col gap-3">
          <p>{answer}</p>
          <div className="flex flex-col gap-2">
            {source_ids && source_ids.length > 0 && (
              <div>Sources: {source_ids.length}</div>
            )}
            {evaluationMetrics && (
              <AnswerEvaluationCards
                groundednessScore={evaluationMetrics.groundedness_score}
                verifiedSentences={evaluationMetrics.verified_sentences}
                totalSentences={evaluationMetrics.total_sentences}
                sourcesUsed={evaluationMetrics.citation_count}
              />
            )}
          </div>
        </div>
      )}
    </Section>
  );
};

export default DisplayAnswer;
