import Badge from './Badge';

const SectionHeaderWithBadge: React.FC<{
  title: string;
  badgeValue: number;
  className?: string;
  headingClassName?: string;
}> = ({ title, badgeValue, className, headingClassName }) => {
  return (
    <div className={`flex items-center gap-2 ${className || ''}`}>
      <h2 className={headingClassName || ''}>{title}</h2>
      <Badge value={badgeValue} />
    </div>
  );
};

export default SectionHeaderWithBadge;
