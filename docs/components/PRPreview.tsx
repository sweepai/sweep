import React from 'react';
import { PR } from '../../types';
import { timeAgo } from '../../utils/timeAgo';

interface PRPreviewProps {
  pr: PR;
}

const PRPreview: React.FC<PRPreviewProps> = ({ pr }) => {
  const [lastUpdated, setLastUpdated] = React.useState<string | null>(null);

  React.useEffect(() => {
    const ttl = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
    const now = new Date().getTime();
    const itemTimestamp = localStorage.getItem(`timestamp-${pr.id}`);

    if (!itemTimestamp || now - itemTimestamp > ttl) {
      localStorage.setItem(`timestamp-${pr.id}`, String(now));
      setLastUpdated(timeAgo(now));
    } else {
      setLastUpdated(timeAgo(Number(itemTimestamp)));
    }
  }, [pr.id]);

  return (
    <div className="pr-preview">
      <h2>{pr.title}</h2>
      <p>Last updated: {lastUpdated}</p>
    </div>
  );
};

export default PRPreview;