// I'm going back to webpack if parcel continues to not want to cooperate

const DEVICE_CODE_ENDPOINT = "https://github.com/login/device/code";
const USER_LOGIN_ENDPOINT = "https://github.com/login/device";
const DEVICE_SUCCESS_URL = "https://github.com/login/device/success";
const OAUTH_ACCESS_TOKEN_ENDPOINT =
  "https://github.com/login/oauth/access_token";
const GITHUB_APP_CLIENT_ID = "Iv1.91fd31586a926a9f";
const MODAL_APP_ENDPOINT = "https://sweepai--prod-ext.modal.run/auth";

const sleep = (ms: number, jitter: number = 300) =>
  new Promise((resolve) => setTimeout(resolve, ms + Math.random() * jitter));

var github_pat = null;
var github_username = null;

chrome.runtime.onInstalled.addListener((details) => {
  console.log("Updated due to ", details.reason);
  chrome.storage.local.get("config", async (result) => {
    if (false && result.config) {
      github_pat = result.config.github_pat;
      github_username = result.config.github_username;
      console.log("Found github_pat and username in storage");
      chrome.tabs.create({ url: "https://github.com/sweepai/sweep/blob/main/docs/extension-post-install.md" });
    } else {
      console.log("No github_pat found... Generating...");
      const device_code_response = await fetch(DEVICE_CODE_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ client_id: GITHUB_APP_CLIENT_ID }),
      });
      const parsedDeviceCodeResponse = new URLSearchParams(
        decodeURIComponent(await device_code_response.text()),
      );
      const parsed_device_code = parsedDeviceCodeResponse.get("user_code");
      console.log("Device code: ", parsed_device_code);
      const tab = await chrome.tabs.create({ url: USER_LOGIN_ENDPOINT });
      const entering_code_execution_results =
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: async (device_code: string) => {
            console.log("Executing script from background.ts");
            console.log(device_code);
            await navigator.clipboard.writeText(device_code);
            device_code.split("").forEach((char, index) => {
              if (char != "-") {
                (
                  document.querySelector(
                    `#user-code-${index}`,
                  ) as HTMLInputElement
                ).value = char;
              }
            });
            const submit_button = document.querySelector(
              "input[type='submit']",
            ) as HTMLButtonElement;
            console.log(submit_button);
            submit_button.click();
          },
          args: [parsed_device_code],
        });
      console.log(entering_code_execution_results);
      await sleep(1500);
      console.log("Done entering code");
      for (var i = 0; i < 40; i += 1) {
        await sleep(500);
        const currentTab = await chrome.tabs.get(tab.id)
        console.log(currentTab.url)
        if (currentTab.url == DEVICE_SUCCESS_URL) {
          break;
        }
      }
      console.log("Done authorizing");
      await chrome.tabs.remove(tab.id);
      chrome.tabs.create({ url: "https://github.com/sweepai/sweep/blob/main/docs/extension-post-install.md" });
      console.log("Closed tab");
      await sleep(1000);
      console.log(parsed_device_code);
      const oauth_access_token_response = await fetch(
        OAUTH_ACCESS_TOKEN_ENDPOINT,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            client_id: GITHUB_APP_CLIENT_ID,
            device_code: parsedDeviceCodeResponse.get("device_code"),
            grant_type: "urn:ietf:params:oauth:grant-type:device_code",
          }),
        },
      );
      const oauth_access_token_raw_response =
        await oauth_access_token_response.text();
      console.log("Raw response: ", oauth_access_token_raw_response);
      const parsedOauthAccessTokenResponse = new URLSearchParams(
        decodeURIComponent(oauth_access_token_raw_response),
      );
      const access_token = parsedOauthAccessTokenResponse.get("access_token");
      console.log("Access token: ", access_token);
      const username_response = await fetch("https://api.github.com/user", {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${access_token}`,
        },
      });
      const github_username = (await username_response.json()).login;
      console.log("Username: ", github_username);
      github_pat = access_token;
      await chrome.storage.local.set({
        config: { github_pat, github_username },
      });
      console.log("Saved GitHub access token and username to storage");
      fetch(MODAL_APP_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: github_username,
          pat: github_pat
        })
      })
    }
  });
});

chrome.runtime.onMessage.addListener(async (request, sender, sendResponse) => {
  if (request.type == "createIssue") {
    const { title: rawTitle, body, repo } = request.issue;
    const title = `Sweep: ${rawTitle}`;
    const tab = await chrome.tabs.create({ url: `https://github.com/${repo}/issues/new` });
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (title, body) => {
        (document.querySelector("#issue_title") as HTMLInputElement).value = title;
        (document.querySelector("#issue_body") as HTMLInputElement).value = body;
        const submitButton = document.querySelector(`#new_issue > div > div > div.Layout-main > div > div.timeline-comment.color-bg-default.hx_comment-box--tip > div > div.flex-items-center.flex-justify-end.d-none.d-md-flex.mx-2.mb-2.px-0 > button`) as HTMLButtonElement;
        submitButton.disabled = false;
        submitButton.click();
      },
      args: [title, body],
    });
    sendResponse({ success: true });
  }
})
