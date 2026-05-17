import DisplaySourcesSkeleton from './DisplaySourcesSkeleton';
import List from './List';
import Section from './Section';
import SourceId from './SourceId';

const DisplaySources = ({
  sources,
  loading = false,
}: {
  sources: { text: string; id: string }[];
  loading?: boolean;
}) => {
  if ((!sources || sources.length === 0) && !loading) {
    return null;
  }

  return (
    <Section title="Sources Used">
      {loading ? (
        <DisplaySourcesSkeleton />
      ) : (
        <List
          items={sources}
          renderItem={(item) => {
            return (
              <div className="flex gap-3 flex-col">
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
      )}
    </Section>
  );
};

export default DisplaySources;
