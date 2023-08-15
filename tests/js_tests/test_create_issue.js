// import Octokit from "@octokit/rest";
const { Octokit } = require("@octokit/core");

(async () => {
  const repo = "kevinlu1248/sweep-landing-page";
  // const repo = "sweepai/sweep";
  const title = `Sweep: Test issue`;
  const body = "";
  const labels = ["sweep"];
  const [owner, repo_name] = repo.split("/");
  // const github_pat = "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"
  const github_pat = "ghu_mYLx32bK2HQy3an1Xo6rtZa2AXjvnF0zfMyb";
  console.log("Found github_pat in storage: ", github_pat)
  const octokit = new Octokit({ auth: github_pat });
  console.log("Sending request...")
  const results = await octokit.request("POST /repos/{owner}/{repo}/issues", {
    owner,
    repo: repo_name,
    title,
    body,
    labels,
    headers: {
      'X-GitHub-Api-Version': '2022-11-28'
    }
  })
  console.log("Received response: ", results)
})();
