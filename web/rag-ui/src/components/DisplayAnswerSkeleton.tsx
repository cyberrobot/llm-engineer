import React from 'react';
import SkeletonBlock from './SkeletonBlock';

const DisplayAnswerSkeleton: React.FC = () => (
  <div className="flex flex-col gap-2">
    <SkeletonBlock height="1.5rem" />
    <SkeletonBlock height="1.5rem" width="60%" />
    <div className="flex items-center gap-2 flex-wrap mt-2">
      <SkeletonBlock height="1.5rem" width="100px" />
      <SkeletonBlock height="1.5rem" width="260px" />
    </div>
  </div>
);

export default DisplayAnswerSkeleton;
