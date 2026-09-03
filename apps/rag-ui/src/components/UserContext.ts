import { createContext, useContext } from 'react';
import type { UserRole } from '../utils/settings';

export type UserContextType = {
  userRole: UserRole;
  setUserRole: (role: UserRole) => void;
};

export const UserContext = createContext<UserContextType | undefined>(undefined);

export const useUser = (): UserContextType => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};
