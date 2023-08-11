import React, { useEffect, useState } from 'react';

export function RepoPreview({ repoName }) {
    const [repoData, setRepoData] = useState(null);
    const headers = {};

    useEffect(() => {
        const fetchRepoData = async () => {
            try {
                const url = `https://api.github.com/repos/${repoName}`;
                const response = await fetch(url, {headers});
                const data = await response.json();
                setRepoData(data);
            } catch (error) {
                console.error("Error fetching repo data:", error);
            }
        };

        if (localStorage) {
            const cacheHit = localStorage.getItem(`repoData-${repoName}`)
            if (cacheHit) {
                const { repoData, timestamp } = JSON.parse(cacheHit)
                if (repoData && timestamp && new Date() - new Date(timestamp) < 1000 * 60 * 60 * 24) {
                    console.log("cache hit")
                    setRepoData(repoData)
                    return
                }
            } 
        }
        console.log("cache miss")
        fetchRepoData();
    }, [repoName]);

    if (!repoData) {
        return <div>Loading...</div>;
    }

    return (
        <div>
            <h2>{repoData.name}</h2>
            <p>{repoData.description}</p>
        </div>
    );
}
