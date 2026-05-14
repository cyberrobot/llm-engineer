import { ChatBubbleLeftEllipsisIcon } from '@heroicons/react/24/outline';
import { useState } from 'react';
import PredefinedQuestion from './components/PredefinedQuestion';
import DisplayAnswer from './components/DisplayAnswer';
import DisplaySources from './components/DisplaySources';
import DisplayInput from './components/DisplayInput';
import DisplayDebug, {
  type Metrics,
  type RetrievedChunk,
} from './components/DisplayDebug';
import { API_URL } from './utils/settings';
import DisplayDebugHistory from './components/DisplayDebugHistory';

type DebugInstance = {
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
  const [debug, setDebug] = useState(null);
  const [loading, setLoading] = useState(false);

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
    setDebug(data.debug);

    setLoading(false);
  };

  const setQueryAndAsk = (str: string = '') => {
    setQuery(str);
    ask(str);
  };

  return (
    <div className="p-5 flex gap-5 flex-col lg:flex-row">
      <div className="lg:max-w-3xl shrink-0 max-w-full">
        <div className="mb-5">
          <div className="flex items-center gap-2 mb-3">
            <ChatBubbleLeftEllipsisIcon className="w-6 h-6 text-accent-bg shrink-0 stroke-2" />
            <h1>RAG Demo</h1>
          </div>
          <h3 className="text-text text-sm font-bold mb-4">
            Ask a question based on your healthcare knowledge base.
          </h3>

          <DisplayInput query={query} queryFn={ask} loading={loading} />
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

        {answer && (
          <DisplayAnswer
            answer={answer.answer}
            source_ids={answer.source_ids}
          />
        )}

        {sources.length > 0 && <DisplaySources sources={sources} />}
      </div>

      {debug && <DisplayDebug debug={debug} />}

      {answer && <DisplayDebugHistory answer={answer} />}
    </div>
  );
}
