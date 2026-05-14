import { useEffect, useState } from 'react';
import { API_URL } from '../utils/settings';
import type { Answer } from '../App';

const DisplayDebugHistory = ({ answer }: { answer: Answer }) => {
  const [auditHistory, setAuditHistory] = useState(null);
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
      setAuditHistory(data);
    };
    fetchData();

    return () => {
      setAuditHistory(null);
    };
  }, [answer]);

  return (
    <div>
      <h2>Retrieval & Generation Debug History</h2>
      {/* <CollapsibleList items={history} /> */}
    </div>
  );
};

export default DisplayDebugHistory;
