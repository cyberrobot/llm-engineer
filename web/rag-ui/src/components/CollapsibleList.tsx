import type { DebugInstance } from '../App';
import { formatDuration, localStringFromUTC } from '../utils/time';
import { useDebugContext } from './DebugContext';
import SkeletonBlock from './SkeletonBlock';

export interface CollapsibleListProps {
  items?: DebugInstance[] | null;
  className?: string;
  loading?: boolean;
}

const CollapsibleList = ({
  items,
  className = '',
  loading,
}: CollapsibleListProps) => {
  if (loading) {
    return <DisplayDebugHistorySkeleton />;
  }

  const { latestDebug, setLatestDebug } = useDebugContext();

  const toggleItem = (index: number) => {
    if (items) {
      setLatestDebug(items[index]);
    }
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {items?.map((item, index) => {
        const isOpen = latestDebug?.id === item.id;
        return (
          <div
            key={item.id}
            className={`overflow-hidden rounded border border-border hover:bg-gray-50 transition-colors duration-300 ease-in-out ${isOpen ? 'bg-gray-50' : 'bg-white'}`}
          >
            <button
              type="button"
              onClick={() => toggleItem(index)}
              className="flex w-full items-center justify-between px-4 py-4 text-left transition cursor-pointer"
            >
              <span className="font-bold">#{item.id}</span>
              <span>{localStringFromUTC(item.timestamp)}</span>
              <span className="font-bold">
                {formatDuration(item.metrics.total_time)}
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default CollapsibleList;

function DisplayDebugHistorySkeleton() {
  return (
    <div className={`space-y-3`}>
      {[...Array(10)].map((_, i) => {
        return (
          <div
            key={i}
            className={`overflow-hidden rounded border border-border hover:bg-gray-50 transition-colors duration-300 ease-in-out`}
          >
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-4 text-left transition cursor-pointer"
            >
              <span className="font-bold">
                <SkeletonBlock height="1.5rem" width="40px" />
              </span>
              <span className="hidden lg:inline">
                <SkeletonBlock height="1.5rem" width="140px" />
              </span>
              <span className="font-bold hidden lg:inline">
                <SkeletonBlock height="1.5rem" width="40px" />
              </span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
