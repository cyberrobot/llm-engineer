import React from 'react';
import type { RetrievedChunk } from './DisplayDebug';
import SkeletonBlock from './SkeletonBlock';
import { ChevronDownIcon } from '@heroicons/react/24/outline';
import SectionHeaderWithBadge from './SectionHeaderWithBadge';

interface DisplayRetrievedChunksProps {
  chunks: RetrievedChunk[];
}

const heading = 'Retrieved Chunks (Raw Retrieval Results)';

const Header = ({ chunks }: { chunks: RetrievedChunk[] }) => {
  return (
    <summary className="flex items-center gap-2 cursor-pointer">
      <SectionHeaderWithBadge
        title={heading}
        badgeValue={chunks.length}
        headingClassName="hover:text-secondary! transition-colors duration-250"
      />
      <ChevronDownIcon
        className={`w-5 h-5 text-secondary duration-300 transition-all group-open:rotate-180`}
      />
    </summary>
  );
};

const DisplayRetrievedChunks: React.FC<DisplayRetrievedChunksProps> = ({
  chunks,
}) => {
  return (
    <details className="group">
      <Header chunks={chunks} />
      <div className="mt-3 rounded overflow-hidden border border-border opacity-0 ease-in-out grid grid-rows-[0fr] group-open:grid-rows-[1fr] group-open:opacity-100 transition-all duration-400">
        <table className="w-7xl lg:w-full border-separate border-spacing-0">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-nowrap p-3 text-text border-b border-r border-border rounded-tl">
                Rank
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                Hybrid Score
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                Distance
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                Keyword Match
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                Source ID
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                Doc ID
              </th>
              <th className="text-nowrap p-3 text-text border-b border-border rounded-tr">
                Preview
              </th>
            </tr>
          </thead>
          <tbody>
            {chunks.map((item, index) => {
              return (
                <tr key={item.id}>
                  <td
                    className={`text-zinc-900 font-semibold p-2 text-center border-b border-r border-border bg-gray-50 ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.rank}
                  </td>
                  <td
                    className={`text-zinc-900 font-semibold p-2 text-center border-b border-r border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.hybrid_score.toFixed(3)}
                  </td>
                  <td
                    className={`p-2 text-center border-b border-r border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.distance.toFixed(3)}
                  </td>
                  <td
                    className={`p-2 text-center border-b border-r border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.keyword_match.toFixed(3)}
                  </td>
                  <td
                    className={`p-2 text-secondary border-b border-r border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.id}
                  </td>
                  <td
                    className={`p-2 text-secondary border-b border-r border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.doc_id}
                  </td>
                  <td
                    className={`p-2 border-border ${index === chunks.length - 1 ? 'border-b-0' : 'border-b'}`}
                  >
                    {item.text_snippet}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
};

export const DisplayRetrievedChunksSkeleton = () => {
  return (
    <div>
      <h3 className="mb-3">{heading}</h3>
      <div className="rounded overflow-x-auto border border-border">
        <table className="w-7xl lg:w-full border-separate border-spacing-0">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-nowrap p-3 text-text border-b border-r border-border rounded-tl">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-r border-border">
                <SkeletonBlock height="1.5rem" />
              </th>
              <th className="text-nowrap p-3 text-text border-b border-border rounded-tr">
                <SkeletonBlock height="1.5rem" />
              </th>
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3].map((_, index) => (
              <tr key={index}>
                <td className="text-zinc-900 font-semibold p-2 text-center border-b border-r border-border bg-gray-50">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="text-zinc-900 font-semibold p-2 text-center border-b border-r border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="p-2 text-center border-b border-r border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="p-2 text-center border-b border-r border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="p-2 text-secondary border-b border-r border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="p-2 text-secondary border-b border-r border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
                <td className="p-2 border-border">
                  <SkeletonBlock height="1.5rem" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DisplayRetrievedChunks;
