import type { ReactNode } from 'react';
import List from './List';
import SkeletonBlock from './SkeletonBlock';
import Badge from './Badge';

type DisplayGeneratedQueriesProps<T extends ReactNode> = {
  items: T[];
  className?: string;
};

const DisplayGeneratedQueries = <T extends ReactNode>({
  items,
}: DisplayGeneratedQueriesProps<T>) => {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h3>Generated Queries (Multi-Query Expansion)</h3>
        <Badge value={items.length} />
      </div>
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
