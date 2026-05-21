import { useState } from 'react';
import PredefinedQuestion from './components/PredefinedQuestion';
import DisplayAnswer from './components/DisplayAnswer';
import DisplaySources from './components/DisplaySources';
import DisplayInput from './components/DisplayInput';
import DisplayDebug, {
  type Metrics,
  type RerankedChunk,
  type RetrievedChunk,
} from './components/DisplayDebug';
import { useDebugContext } from './components/DebugContext';
import Header from './components/Header';
import { useUser } from './components/UserContext';
import { getRagChat } from './services/getRagChat';

export type DebugInstance = {
  id: string;
  timestamp: string;
  user_role: string;
  question: string;
  reply: {
    answer: string;
    source_ids: string[];
  };
  metrics: Metrics;
  queries: string[];
  retrieved_chunks: RetrievedChunk[];
  reranked_chunks: RerankedChunk[];
};

export type Answer = {
  answer: string;
  source_ids: string[];
};

export default function App() {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const { refreshDebugHistory, setDebugHistoryLoading } = useDebugContext();
  const { userRole } = useUser();

  const q1 = 'What procedures should staff follow before performing surgery?';
  const q2 =
    'What checks are required before approving a large international payment?';
  const q3 =
    'How should support agents handle customer complaints about delayed deliveries?';

  const ask = async (str: string = '') => {
    setLoading(true);
    setDebugHistoryLoading(true);

    try {
      const data = await getRagChat({
        query: str,
        userRole: userRole,
      });

      setAnswer(data.reply);
      setSources(data.sources || []);
      refreshDebugHistory();
      setLoading(false);
    } catch (error) {
      setAnswer({
        answer: 'Error fetching answer. Please try again.',
        source_ids: [],
      });
      setSources([]);
      setLoading(false);
      setDebugHistoryLoading(false);
    }
  };

  const setQueryAndAsk = (str: string = '') => {
    setQuery(str);
    ask(str);
  };

  return (
    <div className="p-5">
      <Header />
      <div className="flex gap-5 flex-col 2xl:flex-row">
        <div className="2xl:w-1/3 w-full">
          <div className="mb-5">
            <div className="max-w-180">
              <DisplayInput query={query} queryFn={ask} loading={loading} />
            </div>
          </div>

          <div className="mb-5 flex gap-3 flex-col lg:flex-row">
            <PredefinedQuestion
              question={q1}
              onClick={setQueryAndAsk}
              disabled={loading}
            />

            <PredefinedQuestion
              question={q2}
              onClick={setQueryAndAsk}
              disabled={loading}
            />

            <PredefinedQuestion
              question={q3}
              onClick={setQueryAndAsk}
              disabled={loading}
            />
          </div>

          <DisplayAnswer
            answer={answer?.answer}
            source_ids={answer?.source_ids}
            loading={loading}
          />

          <DisplaySources loading={loading} sources={sources} />
        </div>

        <div className="w-full 2xl:w-2/3">
          <DisplayDebug />
        </div>
      </div>
    </div>
  );
}
