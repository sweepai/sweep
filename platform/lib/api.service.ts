export const getFiles = async (
  repoName: string,
  blockedGlobs: string,
  limit: number = 10000,
) => {
  const url = "/api/files/list";
  const body = {
    repo: repoName,
    blockedGlobs: blockedGlobs.split(",").map((s) => s.trim()),
    limit,
  };
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return await response.json();
};

export const getFile = async (repoName: string, filePath: string) => {
  const url = "/api/files";
  const params = new URLSearchParams({ repo: repoName, filePath }).toString();
  const response = await fetch(url + "?" + params);
  console.log("response", response);
  const object = await response.json();
  return object;
};

export const writeFile = async (
  repoName: string,
  filePath: string,
  newContent: string,
) => {
  const url = "/api/files";
  const body = {
    repo: repoName,
    filePath,
    newContent,
  };
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const object = await response.json();
  return object;
};

const runSingleScript = async (
  repo: string,
  filePath: string,
  script: string,
) => {
  const url = "/api/run";
  const body = {
    repo,
    filePath,
    script,
  };
  const response = await fetch(url, {
    method: "POST",
    body: JSON.stringify(body),
  });
  const object = await response.json();
  return object;
};

export const runScript = async (
  repo: string,
  filePath: string,
  script: string,
  file?: string,
) => {
  // sorry for the mess
  if (!file) {
    return runSingleScript(repo, filePath, script);
  }
  const { contents: oldContents } = await getFile(repo, filePath);
  console.log(oldContents);
  await writeFile(repo, filePath, file);
  const object = await runSingleScript(repo, filePath, script);
  await writeFile(repo, filePath, oldContents);
  return object;
};

export default getFiles;
