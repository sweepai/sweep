import App from "./App";
import GitHubAutocomplete from "./Autocomplete";
import { createRoot } from "react-dom/client";

const issueCreatorRootNode = document.createElement("div");
issueCreatorRootNode.id = "root";
const issueCreatorQuerySelector =
  "#repo-content-pjax-container > div > div > div.Layout.Layout--flowRow-until-md.Layout--sidebarPosition-end.Layout--sidebarPosition-flowRow-end > div.Layout-main";
const issueCreatorMainDiv = document.querySelector(issueCreatorQuerySelector);

if (issueCreatorMainDiv) {
  issueCreatorMainDiv.prepend(issueCreatorRootNode);
  const issueCreatorRoot = createRoot(issueCreatorRootNode);
  issueCreatorRoot.render(<App />);
}

const autocompleteRootNode = document.createElement("div");
issueCreatorRootNode.id = "root";
const autocompleteQuerySelector = "body";
const autocompleteMainDiv = document.querySelector(autocompleteQuerySelector);

if (autocompleteMainDiv) {
  console.log("autocompleteMainDiv found")
  autocompleteMainDiv.prepend(autocompleteRootNode)
  const autocompleteRoot = createRoot(autocompleteRootNode)
  autocompleteRoot.render(<GitHubAutocomplete />)
}
