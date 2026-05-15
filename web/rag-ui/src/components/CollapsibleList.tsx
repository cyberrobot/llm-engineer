import { useState, type ReactNode } from 'react';
import type { DebugInstance } from '../App';
import { formatDuration, localStringFromUTC } from '../utils/time';
import { ChevronDownIcon } from '@heroicons/react/24/outline';
import { cacheBooleanToString } from '../utils/display';

export interface CollapsibleListProps {
  items: DebugInstance[];
  className?: string;
}

const CollapsibleListContentItem = ({
  title,
  value,
}: {
  title: string;
  value: string | number | ReactNode;
}) => {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-text font-semibold">{title}</span>
      <span className="font-bold">{value}</span>
    </div>
  );
};

const CollapsibleList = ({ items, className = '' }: CollapsibleListProps) => {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const toggleItem = (index: number) => {
    setOpenIndex((current) => (current === index ? null : index));
  };

  return (
    <div className={`space-y-3 ${className}`}>
      {items.map((item, index) => {
        const isOpen = openIndex === index;
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
              <ChevronDownIcon
                className={`transition-transform duration-200 size-4 ${isOpen ? 'rotate-180' : 'rotate-0'}`}
              />
            </button>
            <div
              className={`overflow-hidden transition-all duration-200 space-y-4 ${
                isOpen ? 'max-h-80 pb-4' : 'max-h-0'
              } px-4`}
            >
              <CollapsibleListContentItem title="Query" value={item.question} />
              <div className="grid grid-cols-4 lg:grid-cols-2 gap-3">
                <CollapsibleListContentItem
                  title="User Role"
                  value={item.user_role}
                />
                <CollapsibleListContentItem
                  title="Cache"
                  value={cacheBooleanToString(item.metrics.cache_hit)}
                />
                <CollapsibleListContentItem
                  title="Queries"
                  value={item.queries.length}
                />
                <CollapsibleListContentItem
                  title="Retrieved Chunks"
                  value={item.retrieved_chunks.length}
                />
                <CollapsibleListContentItem
                  title="Total Time"
                  value={formatDuration(item.metrics.total_time)}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default CollapsibleList;
