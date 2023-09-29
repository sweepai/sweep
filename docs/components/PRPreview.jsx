import { useState, useEffect } from "react";
import parse from "parse-diff";
import { ShowMore } from "./ShowMore";
import { BiGitMerge } from "react-icons/bi";
import { FiCornerDownRight } from "react-icons/fi";


export function PRPreview({ repoName, prId }) {
    const [prData, setPrData] = useState(null)
    const [issueData, setIssueData] = useState(null)
    const [diffData, setDiffData] = useState(null)
    const key = `prData-${repoName}-${prId}-v0`;
    const herokuAnywhere = "https://sweep-examples-cors-143adb2b6ffb.herokuapp.com/"
    const headers = {}

    useEffect(() => {
        const fetchPRData = async () => {
            try {
                const url = `https://api.github.com/repos/${repoName}/pulls/${prId}`;
                console.log(url)
                const response = await fetch(url, {headers});
                console.log(response)
                const data = await response.json();
                console.log("pr data", data)
                setPrData(data);

                if (!data.body) {
                    return;
                }

                const content = data.body
                const issueId = data.body.match(/Fixes #(\d+)/)[1]

                if (!issueId) {
                    return;
                }

                const issuesUrl = `https://api.github.com/repos/${repoName}/issues/${issueId}`
                const issueResponse = await fetch(issuesUrl, {headers});
                const issueData = await issueResponse.json();
                setIssueData(issueData);
                console.log("issueData", issueData)

                // const diffResponse = await fetch(herokuAnywhere + data.diff_url); // need better cors solution
                const diffResponse = await fetch(`${herokuAnywhere}${data.diff_url}`); // need better cors solution
                const diffText = await diffResponse.text();
                setDiffData(diffText);

                if (!data.diff_url) {
                    return;
                }

            } catch (error) {
                console.error("Error fetching PR data:", error);
            }
        };

        console.log(localStorage);
        if (localStorage) {
            try {
                const cacheHit = localStorage.getItem(key)
                if (cacheHit) {
                    const { prData, diffData, issueData, timestamp } = JSON.parse(cacheHit)
                    if (prData && diffData && issueData && timestamp && new Date() - new Date(timestamp) < 1000 * 60 * 60 * 24) {
                        console.log("cache hit")
                        setPrData(prData)
                        setDiffData(diffData)
                        setIssueData(issueData)
                        return
                    }
                }
            } catch (error) {
                console.error("Error parsing cache hit:", error);
            }
        }
        console.log("cache miss")
        fetchPRData();
    }, [repoName, prId]);

    useEffect(() => {
        console.log(localStorage);
        if (localStorage && prData && diffData && issueData) {
            const data = {
                prData,
                diffData,
                issueData,
                timestamp: new Date(),
            }
            localStorage.setItem(key, JSON.stringify(data))
        }
    }, [prData, diffData, issueData]);

    if (!prData || !prData.user) {
        return <div>{`https://github.com/${repoName}/pulls/${prId}`}. Loading...</div>;
    }

    const numberDaysAgoMerged = Math.max(Math.round((new Date() - new Date(prData.merged_at)) / (1000 * 60 * 60 * 24)), 71)
    const parsedDiff = parse(diffData)
    var issueTitle = issueData != null ? issueData.title.replace("Sweep: ", "") : ""
    issueTitle = issueTitle.charAt(0).toUpperCase() + issueTitle.slice(1);
    console.log("parsedDiff", parsedDiff)

    return (
        <>
            <style>
                {`
                    .hoverEffect:hover {
                        // background-color: #222;
                    }
                    h5 ::after {
                        display: none;
                    }
                    .clickable {
                        cursor: pointer;
                    }
                    .clickable:hover {
                        text-decoration: underline;
                    }
                `}
            </style>
            <div
                className="hoverEffect"
                style={{
                    border: "1px solid darkgrey",
                    borderRadius: 5,
                    marginTop: 32,
                    padding: 10,
                }}
            >
                <div style={{display: "flex"}}>
                    <h5
                        className="clickable" style={{marginTop: 0, fontWeight: "bold", fontSize: 18}}
                        onClick={() => window.open(prData.html_url, "_blank")}
                    >
                        {prData.title}
                    </h5>
                    <span style={{color: "#815b9e", marginTop: 2, display: "flex"}}>
                        &nbsp;&nbsp;
                        <BiGitMerge style={{marginTop: 3}}/>
                        &nbsp;Merged
                    </span>
                </div>
                {
                    prData && (
                        <div style={{display: "flex", color: "#666"}}>
                            #{prId} •&nbsp;<span className="clickable" onClick={() => window.open("https://github.com/apps/sweep-ai")}>{prData.user && prData.user.login}</span>&nbsp;•&nbsp;<BiGitMerge style={{marginTop: 3}}/>&nbsp;Merged {numberDaysAgoMerged} days ago by&nbsp;<span className="clickable" onClick={() => window.open(`https://github.com/${prData.mergedBy && prData.merged_by.login || "wwzeng1"}`, "_blank")}>{prData.mergedBy && prData.merged_by.login || "wwzeng1"}</span>
                        </div>
                    )
                }
                <div style={{display: "flex", marginTop: 15, color: "darkgrey"}}>
                    <FiCornerDownRight style={{marginTop: 3 }} />&nbsp;{issueData && <p className="clickable">Fixes #{issueData.number} • {issueTitle}</p>}
                </div>
                {diffData && (
                    <>
                        <hr style={{borderColor: "darkgrey", margin: 20}}/>
                        <ShowMore>
                            <div
                                className="codeBlocks"
                                style={{
                                    borderRadius: 5,
                                    padding: 10,
                                    transition: "background-color 0.2s linear",
                                }}
                            >
                                {parsedDiff.map(({chunks, from, oldStart}) => (
                                    from !== "/dev/null" && from !== "sweep.yaml" &&
                                    <>
                                        <p style={{
                                            marginTop: 0,
                                            marginBottom: 0,
                                            fontFamily: "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace"
                                        }}>{from}</p>
                                        {chunks.map(({changes}) =>
                                            <pre style={{
                                                backgroundColor: "#161717",
                                                borderRadius: 10,
                                                whiteSpace: "pre-wrap",
                                            }}>
                                                {changes.map(({content, type}) =>
                                                    <>
                                                        {type === "add" && content && <div style={{backgroundColor: "#12261e", width: "100%", padding: 4}}>{content}</div>}
                                                        {type === "del" && content && <div style={{backgroundColor: "#25171c", width: "100%", padding: 4}}>{content}</div>}
                                                        {type === "normal" && content && <div style={{padding: 4}}>{content}</div>}
                                                    </>
                                                )}
                                            </pre>
                                        )}
                                    </>
                                ))}
                            </div>
                        </ShowMore>
                    </>
                )}
            </div>
        </>
    )
}
