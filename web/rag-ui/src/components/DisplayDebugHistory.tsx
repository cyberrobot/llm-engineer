import React from 'react';

interface DisplayDebugHistoryProps {
  history: string[];
}

const DisplayDebugHistory: React.FC<DisplayDebugHistoryProps> = ({
  history,
}) => {
  return (
    <div>
      <h2>Retrieval £ Generation Debug History</h2>
      <ul>
        {history.map((entry, index) => (
          <li key={index}>{entry}</li>
        ))}
      </ul>
    </div>
  );
};

export default DisplayDebugHistory;
