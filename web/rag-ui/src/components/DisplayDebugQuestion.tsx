import List from './List';
import SkeletonBlock from './SkeletonBlock';

type DisplayDebugQuestionProps = {
  question: string;
  className?: string;
};

const DisplayDebugQuestion = ({ question }: DisplayDebugQuestionProps) => {
  return (
    <div>
      <h3 className="mb-3">Question Asked</h3>
      <List
        items={[question]}
        renderItem={(item) => {
          return <span>{item}</span>;
        }}
      />
    </div>
  );
};

export default DisplayDebugQuestion;

export function DisplayDebugQuestionSkeleton() {
  return (
    <div>
      <h3 className="mb-3">Question Asked</h3>
      <div>
        <List
          items={[1]}
          renderItem={() => {
            return <SkeletonBlock height="1.5rem" width="80%" />;
          }}
        />
      </div>
    </div>
  );
}
