import { useEffect, useState } from 'react';
import { API_URL } from '../utils/settings';
import type { DebugInstance } from '../App';
import CollapsibleList from './CollapsibleList';
import { useDebugContext } from './DebugContext';

const DisplayDebugHistory = () => {
  const { refreshCount, setLatestDebug, setDebugHistoryLoading, loading } =
    useDebugContext();
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
      if (data && data.length > 0) {
        setDebugHistory(data);
        setLatestDebug(data[0]);
        setDebugHistoryLoading(false);
      }
    };
    setDebugHistoryLoading(true);
    fetchData();

    return () => {
      setDebugHistory(null);
      setDebugHistoryLoading(false);
    };
  }, [refreshCount]);

  return <CollapsibleList loading={loading} items={debugHistory} />;
};

export default DisplayDebugHistory;
