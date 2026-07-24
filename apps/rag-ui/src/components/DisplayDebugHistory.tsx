import { useEffect, useState } from 'react';
import type { DebugInstance } from '../App';
import { useDebugContext } from './DebugContext';
import DebugHistoryTimeline from './DebugHistoryTimeline';
import { getAuditLogs } from '../services/getAuditLogs';

const DisplayDebugHistory = () => {
  const { refreshCount, setLatestDebug, setDebugHistoryLoading, loading } =
    useDebugContext();
  const [debugHistory, setDebugHistory] = useState<DebugInstance[] | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      setDebugHistoryLoading(true);

      try {
        const data = await getAuditLogs();

        if (!cancelled && data && data.length > 0) {
          setDebugHistory(data);
          setLatestDebug(data[0]);
        }
      } finally {
        if (!cancelled) {
          setDebugHistoryLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
      setDebugHistory(null);
      setDebugHistoryLoading(false);
    };
  }, [refreshCount, setDebugHistoryLoading, setLatestDebug]);

  return <DebugHistoryTimeline loading={loading} items={debugHistory} />;
};

export default DisplayDebugHistory;
