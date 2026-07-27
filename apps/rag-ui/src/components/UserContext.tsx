import React, { createContext, useState, type ReactNode } from 'react';
import { USER_ROLES } from '../utils/settings';

interface UserContextType {
  userRole: string;
  setUserRole: (role: string) => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export const UserProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const [userRole, setUserRole] = useState<string>(USER_ROLES[0]);

  return (
    <UserContext.Provider value={{ userRole, setUserRole }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = (): UserContextType => {
  const context = React.useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

export default UserContext;
