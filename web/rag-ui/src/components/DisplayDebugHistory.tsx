import { useEffect, useState } from 'react';
import { API_URL } from '../utils/settings';
import type { Answer, DebugInstance } from '../App';
import CollapsibleList from './CollapsibleList';

const DisplayDebugHistory = ({ answer }: { answer: Answer }) => {
  const [debugHistory, setDebugHistory] = useState<DebugInstance[] | null>(
    null,
  );
  const getDebugHistory = async () => {
    const res = await fetch(`${API_URL}/audit-logs`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    return await res.json();
  };

  useEffect(() => {
    const fetchData = async () => {
      const data = await getDebugHistory();
      setDebugHistory(data);
    };
    fetchData();

    return () => {
      setDebugHistory(null);
    };
  }, [answer]);

  return (
    <div>
      <h3 className="mb-3">Retrieval & Generation Debug History</h3>
      {debugHistory && <CollapsibleList items={debugHistory} />}
    </div>
  );
};

export default DisplayDebugHistory;
