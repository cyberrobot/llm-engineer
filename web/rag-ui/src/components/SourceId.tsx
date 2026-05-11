const SourceId = ({ id }: { id: string }) => {
  return (
    <span className="border border-secondary px-2 py-0.5 rounded-md bg-secondary-bg text-secondary text-sm lg:whitespace-nowrap">
      {id}
    </span>
  );
};

export default SourceId;
