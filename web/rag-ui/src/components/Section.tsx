import type { ReactNode } from 'react';

const Section = ({
  title,
  children,
  className = '',
}: {
  title?: ReactNode | string;
  className?: string;
  children: React.ReactNode | React.ReactNode[] | string | undefined;
}) => {
  return (
    <div className={`mb-5 border border-border rounded px-4 py-3 ${className}`}>
      {typeof title === 'string' ? <h2 className="mb-3">{title}</h2> : title}
      {children}
    </div>
  );
};

export default Section;
