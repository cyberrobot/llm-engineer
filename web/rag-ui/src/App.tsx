import { ChatBubbleLeftEllipsisIcon } from '@heroicons/react/16/solid';
import { useState } from 'react';
import PredefinedQuestion from './components/PredefinedQuestion';
import { PlayIcon } from '@heroicons/react/24/outline';
import DisplayAnswer from './components/DisplayAnswer';
import DisplaySources from './components/DisplaySources';
const API_URL = import.meta.env.VITE_API_URL;

export default function App() {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState<{
    answer: string;
    source_ids: string[];
  } | null>(null);
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

  const inputAndAsk = (str: string = '') => {
    setQuery(str);
    ask(str);
  };

  return (
    <div style={{ padding: 20, fontFamily: 'Arial' }}>
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-3">
          <ChatBubbleLeftEllipsisIcon className="w-6 h-6 text-accent-bg shrink-0" />
          <h1>RAG Demo</h1>
        </div>
        <h3 className="text-text text-sm font-bold mb-4">
          Ask a question based on your healthcare knowledge base.
        </h3>

        <div className="flex items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-100 px-3 py-2 text-base border border-border bg-bg rounded box-border text-text"
            placeholder="Ask something..."
          />
          <button
            onClick={() => ask()}
            disabled={loading}
            className="py-2 px-4 text-base border border-accent-border bg-accent-bg text-accent rounded cursor-pointer hover:bg-secondary-bg hover:border-accent-border hover:text-secondary disabled:bg-bg disabled:border-border disabled:text-text transition-all duration-600 ease-in-out flex items-center gap-1"
          >
            <PlayIcon className="w-5 h-5" /> {loading ? 'Loading...' : ' Ask'}
          </button>
        </div>
      </div>

      <div className="mb-5 flex gap-3 flex-col lg:flex-row">
        <PredefinedQuestion
          question={q1}
          onClick={inputAndAsk}
          disabled={loading}
        />

        <PredefinedQuestion
          question={q2}
          onClick={inputAndAsk}
          disabled={loading}
        />

        <PredefinedQuestion
          question={q3}
          onClick={inputAndAsk}
          disabled={loading}
        />
      </div>

      {answer && (
        <DisplayAnswer answer={answer.answer} source_ids={answer.source_ids} />
      )}

      {sources.length > 0 && <DisplaySources sources={sources} />}

      {debug && (
        <div className="section">
          <h2>Debug</h2>
          <pre className="debug">{JSON.stringify(debug, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
