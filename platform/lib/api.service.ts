

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
    const body = {
        filePath
    }
    const params = new URLSearchParams({repo: "/root/sweep", filePath}).toString();
    const response = await fetch(url + "?" +params)
    console.log("response", response)
    const object = await response.json()
    console.log(object)
    return object
}



export default getFiles