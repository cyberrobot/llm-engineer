import React from 'react';

type ListProps<T> = {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  className?: string;
};

const List = <T,>({ items, renderItem, className }: ListProps<T>) => {
  return (
    <ul className={`mb-5 border border-border bg-gray-50 rounded ${className}`}>
      {items.map((item, index) => (
        <li
          key={index}
          className={`border-b border-border p-3 ${index === items.length - 1 ? 'border-b-0' : ''}`}
        >
          {renderItem(item, index)}
        </li>
      ))}
    </ul>
  );
};

export default List;
