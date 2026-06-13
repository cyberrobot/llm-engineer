import {
  CheckCircleIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import type { ReactNode } from 'react';
import Card from './Card';
import SkeletonBlock from './SkeletonBlock';

type AnswerEvaluationCardsProps = {
  groundednessScore: number;
  verifiedSentences: number;
  totalSentences: number;
  sourcesUsed: number;
};

type EvaluationCardProps = {
  icon: ReactNode;
  iconBackgroundClassName: string;
  title: string;
  value: ReactNode;
  description: string;
};

const AnswerEvaluationCards = ({
  groundednessScore,
  verifiedSentences,
  totalSentences,
  sourcesUsed,
}: AnswerEvaluationCardsProps) => {
  const cards: EvaluationCardProps[] = [
    {
      icon: <ShieldCheckIcon className="size-6 text-green-500 stroke-2" />,
      iconBackgroundClassName:
        'bg-gradient-to-br from-green-500/20 via-green-500/10 to-green-500/5',
      title: 'Trust Score',
      value: groundednessScore * 100 + '%',
      description: 'Grounded in sources',
    },
    {
      icon: <CheckCircleIcon className="size-6 text-secondary stroke-2" />,
      iconBackgroundClassName:
        'bg-gradient-to-br from-secondary/20 via-secondary/10 to-secondary/5',
      title: 'Verified Claims',
      value: `${verifiedSentences} / ${totalSentences}`,
      description: 'Sentences supported',
    },
    {
      icon: <DocumentTextIcon className="size-6 text-blue-500 stroke-2" />,
      iconBackgroundClassName:
        'bg-gradient-to-br from-blue-500/20 via-blue-500/10 to-blue-500/5',
      title: 'Sources Used',
      value: sourcesUsed,
      description: 'Unique sources',
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.title} className="flex items-start gap-3 p-3">
          <div
            className={`flex size-10 shrink-0 items-center justify-center rounded-full ${card.iconBackgroundClassName}`}
          >
            {card.icon}
          </div>
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-xs font-semibold text-text">
              {card.title}
            </span>
            <span className="break-words text-lg font-bold">{card.value}</span>
            <span className="text-xs text-gray-500">{card.description}</span>
          </div>
        </Card>
      ))}
    </div>
  );
};

export default AnswerEvaluationCards;

export const AnswerEvaluationCardsSkeleton = () => {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {[...Array(3)].map((_, index) => (
        <Card key={index} className="flex items-start gap-3 p-3">
          <SkeletonBlock
            width="2.5rem"
            height="2.5rem"
            className="shrink-0 rounded-full"
          />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <SkeletonBlock height="1rem" width="70%" />
            <SkeletonBlock height="1.5rem" width="45%" />
            <SkeletonBlock height="1rem" width="85%" />
          </div>
        </Card>
      ))}
    </div>
  );
};
