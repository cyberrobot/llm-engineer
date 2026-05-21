const Badge = ({
  value,
  className,
}: {
  value: string | number;
  className?: string;
}) => {
  return (
    <span
      className={`border border-secondary px-2 py-0.5 rounded-md bg-secondary-bg text-secondary lg:whitespace-nowrap ${className || ''}`}
    >
      {value}
    </span>
  );
};

export default Badge;
