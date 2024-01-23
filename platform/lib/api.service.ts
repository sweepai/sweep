

export const getFiles = async () => {
    const url = "/api/files/list";
    const body = {
        repo: "/root/sweep"
    }
    const response = await fetch(url, {
        method: "POST",
        body: JSON.stringify(body)
    })
    return await response.json()
}

export const getFile = async (filePath: string) => {
    const url = "/api/files";
    const params = new URLSearchParams({repo: "/root/sweep", filePath}).toString();
    const response = await fetch(url + "?" +params)
    console.log("response", response)
    const object = await response.json()
    console.log(object)
    return object
}

export const runScript = async (repo: string, filePath: string, script: string) => {
    const url = "/api/run";
    const body = {
        repo,
        filePath,
        script,
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