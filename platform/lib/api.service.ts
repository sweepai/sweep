

export const getFiles = async (repoName: string) => {
    const url = "/api/files/list";
    const body = {repo: repoName}
    const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify(body)
    })
    return await response.json()
}

export const getFile = async (repoName: string, filePath: string) => {
    const url = "/api/files";
    const params = new URLSearchParams({repo: repoName, filePath}).toString();
    const response = await fetch(url + "?" +params)
    console.log("response", response)
    const object = await response.json()
    console.log(object)
    return object
}

const runSingleScript = async (repo: string, filePath: string, script: string) => {
    const url = "/api/run";
    const body = {
        repo,
        filePath,
        script,
    }
    const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify(body)
    })
    const object = await response.json()
    return object
}

var escapeShell = (cmd: string) => {
    return '"'+cmd.replace(/(["'$`\\])/g,'\\$1')+'"';
  };


export const runScript = async (repo: string, filePath: string, script: string, file?: string) => {
    // sorry for the mess
    if (!file) {
        return runSingleScript(repo, filePath, script)
    }
    const { stdout: oldFile } = await runSingleScript(repo, filePath, `cat $FILE_PATH`)
    await runSingleScript(repo, filePath, `echo "${escapeShell(file)}" > $FILE_PATH`)
    const { stdout: newOldFile } = await runSingleScript(repo, filePath, `cat $FILE_PATH`)
    console.log(newOldFile)
    const object = await runSingleScript(repo, filePath, script)
    await runSingleScript(repo, filePath, `echo "${escapeShell(oldFile)}" > $FILE_PATH`)
    return object
}



export default getFiles
