import type { ReactNode } from 'react';
import List from './List';

type DisplayGeneratedQueriesProps<T extends ReactNode> = {
  items: T[];
  className?: string;
};

const DisplayGeneratedQueries = <T extends ReactNode>({
  items,
  className,
}: DisplayGeneratedQueriesProps<T>) => {
  return (
    <div className={className}>
      <h3 className="mb-3">Generated Queries (Multi-Query Expansion)</h3>
      <List
        items={items}
        renderItem={(item) => {
          return <span>{item}</span>;
        }}
      />
    </div>
  );
};

export default DisplayGeneratedQueries;
