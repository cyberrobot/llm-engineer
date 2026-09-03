import RobotIcon from '../assets/robot.svg?react';
import UserRoleDropdown from './UserRoleDropdown';

const Header = () => {
  return (
    <div className="flex justify-between items-start gap-2">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <RobotIcon className="w-6 h-6 text-accent-bg shrink-0 stroke-2" />
          <h1>RAG Demo</h1>
        </div>
        <h3 className="text-text text-sm font-bold mb-4">
          Ask a question based on your healthcare knowledge base.
        </h3>
      </div>
      <UserRoleDropdown />
    </div>
  );
};

export default Header;
