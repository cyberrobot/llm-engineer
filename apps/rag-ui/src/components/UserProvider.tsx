import { useState, type ReactNode } from 'react';
import { USER_ROLES, type UserRole } from '../utils/settings';
import { UserContext } from './UserContext';

const UserProvider = ({ children }: { children: ReactNode }) => {
  const [userRole, setUserRole] = useState<UserRole>(USER_ROLES[0]);

  return (
    <UserContext.Provider value={{ userRole, setUserRole }}>
      {children}
    </UserContext.Provider>
  );
};

export default UserProvider;
