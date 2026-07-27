import React from 'react';
import Card from './Card';

type ListProps<T> = {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  className?: string;
};

const List = <T,>({ items, renderItem, className }: ListProps<T>) => {
  return (
    <Card as="ul" className={className}>
      {items.map((item, index) => (
        <li
          key={index}
          className={`border-b border-border p-3 ${index === items.length - 1 ? 'border-b-0' : ''}`}
        >
          {renderItem(item, index)}
        </li>
      ))}
    </Card>
  );
};

export default List;
