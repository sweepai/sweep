import React, { useState, useEffect } from 'react'

export function RepoPreview({ repoName, displayName=null }) {
    const [repoData, setRepoData] = useState(null)
    const key = `repoData-${repoName}-v0`
    const headers = {}

    if (!displayName) {
        displayName = repoName.split("/")[1]
        displayName = displayName.charAt(0).toUpperCase() + displayName.slice(1);
    }

    useEffect(() => {
        const fetchRepoData = async () => {
            const url = `https://api.github.com/repos/${repoName}`
            const response = await fetch(url, {headers})
            const data = await response.json()
            console.log("repo data", data)
            setRepoData(data)
        }
        if (localStorage) {
            try {
                const cacheHit = localStorage.getItem(key)
                if (cacheHit) {
                    const { repoData, timestamp } = JSON.parse(cacheHit)
                    if (repoData && timestamp && new Date() - new Date(timestamp) < 1000 * 60 * 60 * 24) {
                        console.log("cache hit")
                        setRepoData(repoData)
                        return
                    }
                }
            } catch (error) {
                console.error("Error parsing cache hit:", error);
            }
        }
        console.log("cache miss")
        fetchRepoData()
    }, [repoName])

    useEffect(() => {
        if (localStorage && repoData) {
            localStorage.setItem(key, JSON.stringify({repoData, timestamp: new Date()}))
        }
    }, [repoData])

    if (!repoData) {
        return <div>{repoName}. Loading...</div>
    }

    const star_count = repoData.stargazers_count
    const star_display = star_count > 1000 ? `${Math.round(star_count / 100) / 10}k` : star_count

    return (
        <>
            <style>
                {`
                    .clickable {
                        cursor: pointer;
                    }
                    .clickable:hover {
                        text-decoration: underline;
                    }
                `}
            </style>
            <div id={repoName} className="clickable" onClick={() => window.open(`https://github.com/${repoName}`)}>
                <h3 id={repoName} style={{ fontSize: "1.5rem", fontWeight: "bold", marginTop: "2rem" }}>
                    {displayName}
                </h3>
                <span style={{color: "darkgrey"}}>
                    {repoData.full_name} • {star_display} stars
                </span>
            </div>
            <h6 style={{color: "darkgrey", marginTop: 8}}>
                {repoData.description}
            </h6>
        </>
    )
}
