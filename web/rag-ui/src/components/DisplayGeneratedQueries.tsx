import type { ReactNode } from 'react';
import List from './List';
import DisplayGeneratedQueriesSkeleton from './DisplayGeneratedQueriesSkeleton';

type DisplayGeneratedQueriesProps<T extends ReactNode> = {
  items: T[];
  className?: string;
  loading?: boolean;
};

const DisplayGeneratedQueries = <T extends ReactNode>({
  items,
  className,
  loading,
}: DisplayGeneratedQueriesProps<T>) => {
  return (
    <div className={className}>
      <h3 className="mb-3">Generated Queries (Multi-Query Expansion)</h3>
      {loading ? (
        <DisplayGeneratedQueriesSkeleton />
      ) : (
        <List
          items={items}
          renderItem={(item) => {
            return <span>{item}</span>;
          }}
        />
      )}
    </div>
  );
};

export default DisplayGeneratedQueries;
