import { useState } from "react"
import { Autocomplete } from "@mui/material";
import Fuse from 'fuse.js';

var options = ['Apple', 'Banana', 'Cherry'];

// (async () => {
//   const tree = await chrome.runtime.sendMessage({
//     type: "enterGithub",
//     repo_full_name: /github\.com\/(?<repo_full_name>[^\/]*?\/[^\/]*?)\/.*/.exec(window.location.href)!["groups"]!["repo_full_name"]
//   })
//   console.log(tree)
// })()

export default function GitHubAutocomplete() {
  const [anchorEl, setAnchorEl] = useState(null);

  const handleInputChange = (event, value) => {
    const words = value.split(' ');
    const lastWord = words[words.length - 1];
    const fuse = new Fuse(options, { includeScore: true });
    const results = fuse.search(lastWord);

    if (results.length > 0 ) {
      setAnchorEl(event.currentTarget);
    } else {
      setAnchorEl(null);
    }
  };

  return (
    <Autocomplete
      freeSolo
      options={options}
      open={Boolean(anchorEl)}
      PopperComponent={({ children }) => (
        <div
          style={{
            position: 'absolute',
            top: anchorEl ? anchorEl.getBoundingClientRect().bottom : 0,
            left: anchorEl ? anchorEl.getBoundingClientRect().right : 0,
            width: 'auto',
          }}
        >
          {children}
        </div>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          onChange={(e) => handleInputChange(e, e.target.value)}
          variant="outlined"
          multiline
          rows={4}
        />
      )}
    />
  );
};
