import type { ReactNode } from 'react';
import List from './List';
import SkeletonBlock from './SkeletonBlock';

type DisplayGeneratedQueriesProps<T extends ReactNode> = {
  items: T[];
  className?: string;
};

const DisplayGeneratedQueries = <T extends ReactNode>({
  items,
}: DisplayGeneratedQueriesProps<T>) => {
  return (
    <div>
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

export function DisplayGeneratedQueriesSkeleton() {
  const widths = ['90%', '40%', '80%'];
  return (
    <div>
      <h3 className="mb-3">Generated Queries (Multi-Query Expansion)</h3>
      <List
        items={[1, 2, 3]}
        renderItem={(_, i) => {
          return <SkeletonBlock height="1.5rem" width={widths[i]} />;
        }}
      />
    </div>
  );
}
