

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

export const runScript = async (repo: string, filePath: string, script: string, file: string) => {
    const url = "/api/run";
    const body = {
        repo,
        filePath,
        script,
        file
    }
    console.log("body!", body)
    const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify(body)
    })
    const object = await response.json()
    console.log("ran script!", object)
    return object
}



export default getFiles
