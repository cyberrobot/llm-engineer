import { useState, type ReactNode } from 'react';

export interface CollapsibleListItem {
  title: string;
  content: ReactNode;
}

export interface CollapsibleListProps {
  items: CollapsibleListItem[];
  className?: string;
}

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
            key={item.title}
            className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
          >
            <button
              type="button"
              onClick={() => toggleItem(index)}
              className="flex w-full items-center justify-between px-4 py-4 text-left text-sm font-semibold text-slate-900 transition hover:bg-slate-50"
            >
              <span>{item.title}</span>
              <span
                className={`inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 text-slate-600 transition-transform duration-200 ${
                  isOpen ? 'rotate-45' : 'rotate-0'
                }`}
              >
                +
              </span>
            </button>
            <div
              className={`overflow-hidden transition-all duration-200 ${
                isOpen ? 'max-h-80 py-4' : 'max-h-0'
              } px-4 text-sm text-slate-700`}
            >
              {item.content}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default CollapsibleList;
