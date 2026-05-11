import Section from './Section';
import SourceId from './SourceId';

const DisplaySources = ({
  sources,
}: {
  sources: { text: string; id: string }[];
}) => {
  return (
    <Section title="Sources Used">
      <div className="-mb-3">
        <Section>
          <div className="-my-3">
            {sources.map((s, i) => (
              <div
                key={i}
                className={`border-b border-border -mx-4 p-3 flex items-center gap-3 flex-col lg:flex-row justify-between ${i === sources.length - 1 ? 'border-b-0' : ''}`}
              >
                <div className="flex items-start lg:items-center gap-3 justify-start w-full lg:w-auto">
                  {`${s.text}`.length >= 150
                    ? `${s.text.slice(0, 150)}...`
                    : s.text}
                </div>
                <div className="flex justify-end w-full lg:w-auto">
                  <SourceId id={s.id} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </Section>
  );
};

export default DisplaySources;
