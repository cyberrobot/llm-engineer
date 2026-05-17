import List from './List';
import SkeletonBlock from './SkeletonBlock';

const DisplaySourcesSkeleton: React.FC = () => {
  return (
    <List
      items={[1]}
      renderItem={() => {
        return (
          <div className="flex gap-3 flex-col">
            <div className="flex items-start lg:items-center gap-3 justify-start w-full lg:w-auto">
              <SkeletonBlock height="1.5rem" />
            </div>
            <div className="flex justify-end w-full lg:w-auto">
              <SkeletonBlock height="1.5rem" width="240px" />
            </div>
          </div>
        );
      }}
    />
  );
};

export default DisplaySourcesSkeleton;
