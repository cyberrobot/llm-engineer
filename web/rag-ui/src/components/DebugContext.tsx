import { createContext, useContext, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { DebugInstance } from '../App';

type DebugContextType = {
  latestDebug: DebugInstance | null;
  setLatestDebug: (d: DebugInstance) => void;
  refreshCount: number;
  refreshDebugHistory: () => void;
};

const DebugContext = createContext<DebugContextType | undefined>(undefined);

export const useDebugContext = () => {
  const ctx = useContext(DebugContext);
  if (!ctx) {
    throw new Error('useDebugContext must be used within a DebugProvider');
  }
  return ctx;
};

export const DebugProvider = ({ children }: { children: ReactNode }) => {
  const [refreshCount, setRefreshCount] = useState(0);
  const [latestDebug, setLatestDebug] = useState<DebugInstance | null>(null);

  const refreshDebugHistory = useCallback(() => {
    setRefreshCount((c) => c + 1);
  }, []);

  return (
    <DebugContext.Provider
      value={{ refreshCount, refreshDebugHistory, latestDebug, setLatestDebug }}
    >
      {children}
    </DebugContext.Provider>
  );
};
