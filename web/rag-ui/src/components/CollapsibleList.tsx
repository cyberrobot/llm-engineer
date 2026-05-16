import type { DebugInstance } from '../App';
import { formatDuration, localStringFromUTC } from '../utils/time';
import { useDebugContext } from './DebugContext';

export interface CollapsibleListProps {
  items: DebugInstance[];
  className?: string;
}

const CollapsibleList = ({ items, className = '' }: CollapsibleListProps) => {
  const { latestDebug, setLatestDebug } = useDebugContext();

  const toggleItem = (index: number) => {
    setLatestDebug(items[index]);
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {items.map((item, index) => {
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
              <span className="hidden lg:inline">
                {localStringFromUTC(item.timestamp)}
              </span>
              <span className="font-bold hidden lg:inline">
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
