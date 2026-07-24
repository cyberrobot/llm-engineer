import React from 'react';

interface SkeletonBlockProps {
  width?: string;
  height?: string;
  className?: string;
  style?: React.CSSProperties;
}

const SkeletonBlock: React.FC<SkeletonBlockProps> = ({
  width = '100%',
  height = '1rem',
  className = '',
  style = {},
}) => (
  <div
    className={`animate-pulse bg-gray-200 rounded ${className}`}
    style={{ width, height, ...style }}
    aria-hidden="true"
  />
);

export default SkeletonBlock;
