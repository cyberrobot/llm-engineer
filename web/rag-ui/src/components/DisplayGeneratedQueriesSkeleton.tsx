import List from './List';
import SkeletonBlock from './SkeletonBlock';

const DisplayGeneratedQueriesSkeleton = () => {
  const widths = ['90%', '40%', '80%'];
  return (
    <List
      items={[1, 2, 3]}
      renderItem={(_, i) => {
        return <SkeletonBlock height="1.5rem" width={widths[i]} />;
      }}
    />
  );
};

export default DisplayGeneratedQueriesSkeleton;
