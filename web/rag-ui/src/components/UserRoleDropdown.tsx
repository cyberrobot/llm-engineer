import { USER_ROLES } from '../utils/settings';
import Dropdown from './Dropdown';
import { useUser } from './UserContext';

const UserRoleDropdown = () => {
  const { userRole, setUserRole } = useUser();
  const dropdownOptions = USER_ROLES.map((role) => ({
    label: role.charAt(0).toUpperCase() + role.slice(1),
    value: role,
  }));

  return (
    <Dropdown
      selected={userRole}
      options={dropdownOptions}
      onChange={setUserRole}
      label="User Role"
    />
  );
};
export default UserRoleDropdown;
