import { useEffect, useState } from 'react';
import type { DebugInstance } from '../App';
import CollapsibleList from './CollapsibleList';
import { useDebugContext } from './DebugContext';
import { getAuditLogs } from '../services/getAuditLogs';

const DisplayDebugHistory = () => {
  const { refreshCount, setLatestDebug, setDebugHistoryLoading, loading } =
    useDebugContext();
  const [debugHistory, setDebugHistory] = useState<DebugInstance[] | null>(
    null,
  );

  useEffect(() => {
    try {
      const fetchData = async () => {
        const data = await getAuditLogs();
        if (data && data.length > 0) {
          setDebugHistory(data);
          setLatestDebug(data[0]);
        }
        setDebugHistoryLoading(false);
      };
      setDebugHistoryLoading(true);
      fetchData();
    } catch (error) {
      setDebugHistoryLoading(false);
    }

    return () => {
      setDebugHistory(null);
      setDebugHistoryLoading(false);
    };
  }, [refreshCount]);

  return <CollapsibleList loading={loading} items={debugHistory} />;
};

export default DisplayDebugHistory;
