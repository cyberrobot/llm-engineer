import React from 'react';
import SkeletonBlock from './SkeletonBlock';
import { AnswerEvaluationCardsSkeleton } from './AnswerEvaluationCards';

const DisplayAnswerSkeleton: React.FC = () => (
  <div className="flex flex-col gap-2">
    <SkeletonBlock height="1.5rem" />
    <SkeletonBlock height="1.5rem" width="60%" />
    <SkeletonBlock height="1.5rem" width="100px" />
    <AnswerEvaluationCardsSkeleton />
  </div>
);

export default DisplayAnswerSkeleton;
