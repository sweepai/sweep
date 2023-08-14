// copied from: https://stackblitz.com/edit/emotion-shadow-dom-example
// goated script

import React, { useState } from "react";
import root from "react-shadow";
import { CacheProvider as EmotionCacheProvider } from "@emotion/react";
import createCache from "@emotion/cache";
import { createTheme, ThemeProvider } from "@mui/material";
import { purple } from "@mui/material/colors";

// Define custom location to insert Emotion styles (instead of document head)
// From: https://emotion.sh/docs/cache-provider

const theme = createTheme({
  palette: {
    primary: {
      main: "#9f7aea",
    },
  },
  components: {
    MuiInputBase: {
      styleOverrides: {
        input: {
          "&::placeholder": {
            color: "white", // Change the placeholder color to your desired color
          },
        },
      },
    },
  },
});

const ShadowDomContainer = ({ children }) => {
  const [emotionCache, setEmotionCache] = useState(null);

  function setEmotionStyles(ref) {
    if (ref && !emotionCache) {
      const createdEmotionWithRef = createCache({
        key: "shadow-dom-styles", // Define a custom key
        container: ref,
      });
      setEmotionCache(createdEmotionWithRef);
    }
  }

  function setShadowRefs(ref) {
    setEmotionStyles(ref);
  }

  return (
    <root.div id="shadow-host">
      <div ref={setShadowRefs} />
      {emotionCache && (
        <ThemeProvider theme={theme}>
          <EmotionCacheProvider value={emotionCache}>
            {children}
          </EmotionCacheProvider>
        </ThemeProvider>
      )}
    </root.div>
  );
};

export default ShadowDomContainer;
