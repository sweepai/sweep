import App from "./App";
import { createRoot } from "react-dom/client";

const rootNode = document.createElement("div");
rootNode.id = "root";
const querySelector =
  "#repo-content-pjax-container > div > div > div.Layout.Layout--flowRow-until-md.Layout--sidebarPosition-end.Layout--sidebarPosition-flowRow-end > div.Layout-main";
const main_div = document.querySelector(querySelector);
if (main_div) {
  main_div.prepend(rootNode);
}

const root = createRoot(rootNode);
root.render(<App />);

chrome.runtime.sendMessage({
  type: "enterGitHub",

})
