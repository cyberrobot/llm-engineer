import List from './List';
import Section from './Section';
import SourceId from './SourceId';

const DisplaySources = ({
  sources,
}: {
  sources: { text: string; id: string }[];
}) => {
  return (
    <Section title="Sources Used">
      <List
        items={sources}
        renderItem={(item) => {
          return (
            <div className="flex items-center gap-3 flex-col lg:flex-row justify-between">
              <div className="flex items-start lg:items-center gap-3 justify-start w-full lg:w-auto">
                {`${item.text}`.length >= 150
                  ? `${item.text.slice(0, 150)}...`
                  : item.text}
              </div>
              <div className="flex justify-end w-full lg:w-auto">
                <SourceId id={item.id} />
              </div>
            </div>
          );
        }}
      />
    </Section>
  );
};

export default DisplaySources;
