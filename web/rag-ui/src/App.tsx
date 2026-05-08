import { useState } from 'react';
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
      <div className="section">
        <h1>RAG Demo</h1>

        <div className="group">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="input"
            placeholder="Ask something..."
          />
          <button onClick={() => ask()} disabled={loading} className="button">
            {loading ? 'Loading...' : 'Ask'}
          </button>
        </div>
      </div>

      <div className="section group">
        <button
          onClick={() => inputAndAsk(q1)}
          disabled={loading}
          className="button"
        >
          {q1}
        </button>

        <button
          onClick={() => inputAndAsk(q2)}
          disabled={loading}
          className="button"
        >
          {q2}
        </button>

        <button
          onClick={() => inputAndAsk(q3)}
          disabled={loading}
          className="button"
        >
          {q3}
        </button>
      </div>

      {answer && (
        <div className="section">
          <h2>Answer</h2>
          <p>{answer.answer}</p>
          {answer.source_ids.length > 0 && (
            <p>Sources: {answer.source_ids.join(', ')}</p>
          )}
        </div>
      )}

      {sources.length > 0 && (
        <div className="section">
          <h2>Sources</h2>
          {sources.map((s, i) => (
            <p key={i}>• {s.text}</p>
          ))}
        </div>
      )}

      {debug && (
        <div className="section">
          <h2>Debug</h2>
          <pre className="debug">{JSON.stringify(debug, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
