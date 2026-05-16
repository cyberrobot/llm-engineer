import { useEffect, useState } from 'react';
import { API_URL } from '../utils/settings';
import type { DebugInstance } from '../App';
import CollapsibleList from './CollapsibleList';
import { useDebugContext } from './DebugContext';

const DisplayDebugHistory = () => {
  const { refreshCount, setLatestDebug } = useDebugContext();
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
      if (data && data.length > 0) {
        setLatestDebug(data[0]);
      }
    };
    fetchData();

    return () => {
      setDebugHistory(null);
    };
  }, [refreshCount]);

  return debugHistory && <CollapsibleList items={debugHistory} />;
};

export default DisplayDebugHistory;
