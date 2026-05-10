import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';

const PredefinedQuestion = ({
  question,
  onClick,
  disabled,
  ...rest
}: {
  question: string;
  onClick: (q: string) => void;
  disabled: boolean;
} & Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  'onClick' | 'disabled'
>) => {
  return (
    <button
      onClick={() => onClick(question)}
      disabled={disabled}
      className={
        `flex 
        gap-2 
        py-3 
        px-4 
        text-base 
        text-left
        border 
        border-accent-border 
        bg-secondary-bg 
        text-secondary 
        rounded 
        cursor-pointer 
        hover:bg-bg 
        hover:border-accent-border 
        hover:text-secondary 
        disabled:bg-bg 
        disabled:border-border 
        disabled:text-text 
        transition-all 
        duration-600 
        ease-in-out` + (rest.className ? ` ${rest.className}` : '')
      }
    >
      <QuestionMarkCircleIcon className="size-6 shrink-0" />
      {question}
    </button>
  );
};

export default PredefinedQuestion;
