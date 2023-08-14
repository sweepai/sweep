// I'm going back to webpack if parcel continues to not want to cooperate

const DEVICE_CODE_ENDPOINT = "https://github.com/login/device/code"
const USER_LOGIN_ENDPOINT = "https://github.com/login/device"
const OAUTH_ACCESS_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
const GITHUB_APP_CLIENT_ID = "Iv1.91fd31586a926a9f";


// device_code_response = requests.post(DEVICE_CODE_ENDPOINT, json={"client_id": GITHUB_APP_CLIENT_ID})
// parsed_device_code_response = parse_qs(unquote(device_code_response.text))
// print("\033[93m" + f"Open {USER_LOGIN_ENDPOINT} if it doesn't open automatically." + "\033[0m")
// print("\033[93m" + f"Paste the following code (copied to your clipboard) and click authorize:" + "\033[0m")
// print("\033[94m" + parsed_device_code_response["user_code"][0] + "\033[0m")  # prints in blue
// print("\033[93m" + "Once you've authorized, ** just wait a few seconds **..." + "\033[0m")  # prints in yellow
// time.sleep(3)
// webbrowser.open_new_tab(USER_LOGIN_ENDPOINT)
// for _ in range(10):
//     time.sleep(5.5)
//     try:
//         oauth_access_token_response = requests.post(
//             OAUTH_ACCESS_TOKEN_ENDPOINT,
//             json={
//                 "client_id": GITHUB_APP_CLIENT_ID,
//                 "device_code": parsed_device_code_response["device_code"][0],
//                 "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
//             }
//         )
//         oauth_access_token_response = parse_qs(unquote(oauth_access_token_response.text))
//         access_token = oauth_access_token_response["access_token"][0]
//         assert access_token
//         break
//     except KeyError:
//         pass
// else:
//     raise Exception("Could not get access token")
// username_response = requests.get(
//     "https://api.github.com/user",
//     headers={
//         "Accept": "application/vnd.github+json",
//         "Authorization": f"Bearer {access_token}",
//     }
// )

// print(
//     "\033[92m" + f"Logged in successfully as {username_response.json()['login']}" + "\033[0m")  # prints in green


var github_pat = null;
chrome.runtime.onInstalled.addListener(() => {
  console.log("installed")
  chrome.storage.local.get("github_pat", async (result) => {
    console.log(result);
    if (result.github_pat) {
      github_pat = result.github_pat;
      console.log(github_pat);
    } else {
      console.log("No github_pat found... Generating...");
      const device_code_response = await fetch(DEVICE_CODE_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ client_id: GITHUB_APP_CLIENT_ID }),
      })
      console.log("device_code_response")
      // console.log(await device_code_response.text())
      const parsedDeviceCodeResponse = new URLSearchParams(decodeURIComponent(await device_code_response.text()));
      const parsed_device_code_response = parsedDeviceCodeResponse.get("user_code");
      // await navigator.clipboard.writeText(parsed_device_code_response);
      console.log(parsed_device_code_response);
      const tab = await chrome.tabs.create({ url: USER_LOGIN_ENDPOINT });
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: async () => {
          await navigator.clipboard.writeText(parsed_device_code_response);
          alert(parsed_device_code_response)
          // navigator.clipboard.readText()
          //   .then(text => {
            (document.activeElement as HTMLInputElement).value = parsed_device_code_response;
            // })
            // .catch(err => console.error('Failed to read clipboard contents: ', err));

        }
      })
    }
  });
});

