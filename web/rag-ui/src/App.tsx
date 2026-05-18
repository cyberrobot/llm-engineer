import { useState } from 'react';
import PredefinedQuestion from './components/PredefinedQuestion';
import DisplayAnswer from './components/DisplayAnswer';
import DisplaySources from './components/DisplaySources';
import DisplayInput from './components/DisplayInput';
import DisplayDebug, {
  type Metrics,
  type RetrievedChunk,
} from './components/DisplayDebug';
import { useDebugContext } from './components/DebugContext';
import { API_URL } from './utils/settings';
import Header from './components/Header';

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
  const { refreshDebugHistory } = useDebugContext();

  const q1 = 'Do medical staff have to disinfect tools before procedures?';
  const q2 = 'Who is allowed to view patient records in the system?';
  const q3 = 'What should be done if a patient shows signs of infection?';

  const ask = async (str: string = '') => {
    setLoading(true);

    const res = await fetch(`${API_URL}/rag-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        message: str || query,
        user_role: 'doctor',
      }),
    });

    const data = await res.json();

    setAnswer(data.reply);
    setSources(data.sources || []);
    refreshDebugHistory();

    setLoading(false);
  };

  const setQueryAndAsk = (str: string = '') => {
    setQuery(str);
    ask(str);
  };

  return (
    <div className="p-5 ">
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
