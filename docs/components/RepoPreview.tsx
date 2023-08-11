import React from 'react';
import { Repo } from '../../types';
import { timeAgo } from '../../utils/timeAgo';

interface RepoPreviewProps {
  repo: Repo;
}

const RepoPreview: React.FC<RepoPreviewProps> = ({ repo }) => {
  const [lastUpdated, setLastUpdated] = React.useState<string | null>(null);

  React.useEffect(() => {
    const ttl = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
    const now = new Date().getTime();
    const itemTimestamp = localStorage.getItem(`timestamp-${repo.id}`);

    if (!itemTimestamp || now - itemTimestamp > ttl) {
      localStorage.setItem(`timestamp-${repo.id}`, String(now));
      setLastUpdated(timeAgo(now));
    } else {
      setLastUpdated(timeAgo(Number(itemTimestamp)));
    }
  }, [repo.id]);

  return (
    <div className="repo-preview">
      {/* Rest of the component */}
    </div>
  );
};

export
