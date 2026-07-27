import { type ReactNode } from 'react';

export const cacheBooleanToString = (value: boolean): ReactNode => {
  return value ? (
    <span className="text-green-500">HIT</span>
  ) : (
    <span className="text-red-500">MISS</span>
  );
};
