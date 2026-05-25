import type { JSX } from 'react/jsx-dev-runtime';
import Badge from './Badge';

const SectionHeaderWithBadge: React.FC<{
  title: string;
  badgeValue?: number;
  className?: string;
  headingClassName?: string;
  loading?: boolean;
  headingLevel?: 1 | 2 | 3 | 4 | 5 | 6;
}> = ({
  title,
  badgeValue,
  className,
  headingClassName,
  loading,
  headingLevel = 2,
}) => {
  const Heading = `h${headingLevel}` as keyof JSX.IntrinsicElements;

  return (
    <div className={`flex items-center gap-2 ${className || ''}`}>
      <Heading className={headingClassName || ''}>{title}</Heading>
      {badgeValue !== undefined && !loading && <Badge value={badgeValue} />}
    </div>
  );
};

export default SectionHeaderWithBadge;
