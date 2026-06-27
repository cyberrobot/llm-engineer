import type { DebugInstance } from '../App';
import { formatDuration, localStringFromUTC } from '../utils/time';
import { useDebugContext } from './DebugContext';
import SkeletonBlock from './SkeletonBlock';

export interface DebugHistoryTimelineProps {
  items?: DebugInstance[] | null;
  className?: string;
  loading?: boolean;
}

const DebugHistoryTimeline = ({
  items,
  className = '',
  loading,
}: DebugHistoryTimelineProps) => {
  const { latestDebug, setLatestDebug } = useDebugContext();

  if (loading) {
    return <DisplayDebugHistorySkeleton className={className} />;
  }

  return (
    <div
      className={`overflow-hidden border border-border bg-white rounded ${className}`}
    >
      {items?.map((item) => {
        const isSelected = latestDebug?.id === item.id;

        return (
          <button
            key={item.id}
            type="button"
            onClick={() => setLatestDebug(item)}
            className={`group relative flex w-full cursor-pointer gap-4 border-b border-border py-5 pr-8 pl-8 text-left transition-colors last:border-b-0 hover:bg-gray-50 ${
              isSelected ? 'bg-gray-50' : 'bg-white'
            }`}
          >
            <span className="absolute top-0 bottom-0 left-9.25 w-px bg-border" />
            <span
              className={`relative z-10 mt-0.5 size-3 shrink-0 rounded-full ring-4 ring-white ${
                isSelected ? 'bg-secondary' : 'bg-gray-300'
              }`}
            />

            <span className="flex min-w-0 flex-1 flex-col gap-3">
              <span className="text-base leading-snug font-semibold text-(--text-h)">
                {item.question}
              </span>
              <span className="flex items-center justify-between gap-4 text-sm font-medium text-text">
                <span>{localStringFromUTC(item.timestamp)}</span>
                <span
                  className={`shrink-0 font-bold ${
                    isSelected ? 'text-secondary' : 'text-text'
                  }`}
                >
                  {formatDuration(item.metrics.total_time)}
                </span>
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default DebugHistoryTimeline;

function DisplayDebugHistorySkeleton({
  className = '',
}: {
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden border border-border bg-white ${className}`}
    >
      {[...Array(7)].map((_, i) => {
        return (
          <div
            key={i}
            className="relative flex gap-4 border-b border-border py-5 pr-8 pl-8 last:border-b-0"
          >
            <span className="absolute top-0 bottom-0 left-9 w-px bg-border" />
            <SkeletonBlock
              width="0.75rem"
              height="0.75rem"
              className="relative z-10 mt-0.5 shrink-0 rounded-full ring-4 ring-white"
            />
            <div className="flex min-w-0 flex-1 flex-col gap-3">
              <SkeletonBlock height="1.25rem" width="85%" />
              <div className="flex items-center justify-between gap-4">
                <SkeletonBlock height="1rem" width="55%" />
                <SkeletonBlock height="1rem" width="3rem" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
