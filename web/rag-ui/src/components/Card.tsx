import type { ElementType, HTMLAttributes, ReactNode } from 'react';

type CardProps = {
  as?: ElementType;
  children?: ReactNode;
  className?: string;
} & HTMLAttributes<HTMLElement>;

const Card = ({
  as: Component = 'div',
  children,
  className = '',
  ...props
}: CardProps) => {
  return (
    <Component
      className={`border border-border bg-gray-50 rounded ${className}`}
      {...props}
    >
      {children}
    </Component>
  );
};

export default Card;
