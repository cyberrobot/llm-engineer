import { useEffect, useRef, useState } from 'react';
import { ChevronDownIcon } from '@heroicons/react/20/solid';
import { UserIcon } from '@heroicons/react/24/outline';

type DropdownOption = {
  label: string;
  value: string;
};

interface DropdownProps {
  options: DropdownOption[];
  selected?: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
}

const Dropdown = ({
  options,
  selected,
  onChange,
  label,
  placeholder = 'Select...',
}: DropdownProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find((option) => option.value === selected);

  return (
    <div className="relative items-center flex" ref={dropdownRef}>
      {label && (
        <span className="hidden md:inline-flex mr-3 font-medium">{label}</span>
      )}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="w-37 inline-flex cursor-pointer justify-between items-center rounded border border-secondary-border bg-secondary-bg px-4 py-2 gap-1 font-medium text-secondary shadow-sm"
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        <span className="inline-flex gap-2">
          <UserIcon className="h-5 w-5 text-secondary stroke-2" />
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDownIcon
          className="ml-2 h-5 w-5 text-secondary"
          aria-hidden="true"
        />
      </button>

      {/* {isOpen && ( */}
      <div
        className={`absolute right-0 top-full z-10 mt-2 w-56 origin-top-right rounded bg-white shadow-lg border-accent-border border transition-all duration-400 ${isOpen ? 'scale-100 opacity-100' : 'scale-95 opacity-0 pointer-events-none'}`}
      >
        <div className="py-1 bg-secondary-bg">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setIsOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-secondary hover:bg-accent-bg hover:text-accent cursor-pointer"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      {/* )} */}
    </div>
  );
};

export default Dropdown;
