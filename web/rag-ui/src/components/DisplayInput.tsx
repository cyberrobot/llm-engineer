import { PlayIcon } from '@heroicons/react/16/solid';
import { useEffect, useState } from 'react';

const DisplayInput = ({
  query,
  queryFn,
  loading,
}: {
  query: string;
  queryFn: (q: string) => void;
  loading: boolean;
}) => {
  const [inputValue, setInputValue] = useState('');

  useEffect(() => {
    setInputValue(query);

    return () => {
      setInputValue('');
    };
  }, [query]);

  return (
    <div className="flex items-center gap-2">
      <input
        type="search"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        className="w-full px-3 py-2 text-base border border-border bg-bg rounded box-border text-text"
        placeholder="Ask something..."
      />
      <button
        onClick={() => queryFn(inputValue)}
        disabled={loading}
        className="py-2 px-4 text-base border border-accent-border bg-accent-bg text-accent rounded cursor-pointer hover:bg-secondary-bg hover:border-accent-border hover:text-secondary disabled:hover:border-accent-border disabled:hover:bg-accent-bg disabled:hover:text-accent transition-all duration-600 ease-in-out flex items-center gap-1"
      >
        {loading ? (
          'Loading...'
        ) : (
          <>
            <PlayIcon className="w-5 h-5" />
            <span>Ask</span>
          </>
        )}
      </button>
    </div>
  );
};

export default DisplayInput;
