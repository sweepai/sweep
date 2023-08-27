from huggingface_hub import InferenceClient
import os
import requests

# API_URL = "https://bnku6rs12vhhd9x3.us-east-1.aws.endpoints.huggingface.cloud"
API_URL = "https://u83egzg5ov3y78l9.us-east-1.aws.endpoints.huggingface.cloud"
# API_URL = "https://bnku6rs12vhhd9x3.us-east-1.aws.endpoints.huggingface.cloud"
# API_URL = "https://edra7if7othaho7k.us-east-1.aws.endpoints.huggingface.cloud"
API_TOKEN = os.environ["HUGGING_FACE_HUB_TOKEN"]
client = InferenceClient(API_URL, token=API_TOKEN)
headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

gen_kwargs = dict(
    max_new_tokens=500,
    stop_sequences=["[/RESP]", "<|endoftext|>", "</s>"],
    # frequency_penalty=0.0,
)

prompt = """\
Your name is Sweep bot and you are to modify the file to complete the task.

Below is the file "src/components/App.tsx".

```
import {
  ChakraProvider,
  Box,
  extendTheme,
  useColorMode,
  ThemeConfig,
} from "@chakra-ui/react";
import CallToAction from "./components/CallToAction";
import { Helmet } from "react-helmet";
import Navbar from "./components/Navbar";
import Banner from "./components/Banner";
import og_image from "./assets/og_image.png";
import { ColorModeSwitcher } from "./ColorModeSwitcher";
import { useEffect } from "react";
import Testimonials from "./components/Testimonials";
import Users from "./components/Users";
import AboutUs from "./components/AboutUs";
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';

import circles from "./assets/circles.svg";
import Features from "./components/Features";
import Conclusion from "./components/Conclusion";

const config: ThemeConfig = {
  initialColorMode: "dark",
  useSystemColorMode: false,
};

const theme = extendTheme({ config });

function ForceDarkMode(props: { children: JSX.Element }) {
  const { colorMode, toggleColorMode } = useColorMode();

  useEffect(() => {
    if (colorMode === "dark") return;
    toggleColorMode();
  }, [colorMode, toggleColorMode]);

  return props.children;
}


export const App = () => {
  useEffect(() => {
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = `(function(){var w=window;var ic=w.Intercom;if(typeof ic==="function"){ic('reattach_activator');ic('update',w.intercomSettings);}else{var d=document;var i=function(){i.c(arguments);};i.q=[];i.c=function(args){i.q.push(args);};w.Intercom=i;var l=function(){var s=d.createElement('script');s.type='text/javascript';s.async=true;s.src='https://widget.intercom.io/widget/ce8fl00z';var x=d.getElementsByTagName('script')[0];x.parentNode.insertBefore(s,x);};if(document.readyState==='complete'){l();}else if(w.attachEvent){w.attachEvent('onload',l);}else{w.addEventListener('load',l,false);}}})();`;
    document.body.appendChild(script);
  }, []);
  return (
    <>
      <Helmet>
        <meta property="og:image" content={og_image} />
        <link rel="icon" type="image/png" sizes="16x16" href="/final-sweep-wizard_16x16.png" />
        <link rel="icon" type="image/png" sizes="32x32" href="/final-sweep-wizard_32x32.png" />
        <link rel="icon" type="image/png" sizes="48x48" href="/final-sweep-wizard_48x48.png" />
        <link rel="icon" type="image/png" sizes="64x64" href="/final-sweep-wizard_64x64.png" />
        <link rel="icon" type="image/png" sizes="128x128" href="/final-sweep-wizard_128x128.png" />
        <link rel="icon" type="image/png" sizes="256x256" href="/final-sweep-wizard_256x256.png" />
      </Helmet>
      <ChakraProvider theme={theme}>
        <ForceDarkMode>
          <Box
            textAlign="center"
            fontSize="xl"
            bgColor="#0d0a1a"
            bgImage={circles}
            bgPos="0 0"
            bgSize="100%"
            minH="100vh"
            bgRepeat="no-repeat"
            overflowX="hidden"
          >
            {false && <ColorModeSwitcher />}
            <Banner />
            <Router>
              <Navbar />
              <Switch>
                <Route exact path="/">
                  <CallToAction />
                  <Users />
                  <Features />
                  <Testimonials />
                  <Conclusion />
                </Route>
                <Route path="/about-us">
                  <AboutUs />
                </Route>
              </Switch>
            </Router>
          </Box>
        </ForceDarkMode>
      </ChakraProvider>
    </>
  );
};
```

### Instructions
Fix the following error logs:

'React' is not defined. (no-undef)

**Format**

Respond by indicating which sections you would like to modify and how you would modify them. Write your response in diff hunks.

This will be applied to the original file. Write the least amount of diffs possible to complete the task in this format:

First hunk:

```diff
line before
- first old code
+ first new code
line after
```

Second hunk:

```diff
line before
- second old code
+ second new code
line after
```

Write multiple small diff hunks instead of one large diff hunk. Only provide the lines necessary and do not just copy the whole file.

### Response

Here is the first diff hunk:
"""


prompt = """\
[INST]
I have the following file `src/example.py` that I would like to modify to complete the task.

```
a = 1
b = 2

class Example:
    def foo(self):
        print("foo")
    def bar(self):
        pass

if __name__ == "__main__":
    Example().foo()
```

Task: Change "foo" to "bar" and increment a.

Respond
[/INST]

[RESP]
Step-by-step thoughts: (max 5 thoughts)
* b should change from 2 to 3.
* The string in the print statement should change from "foo" to "bar".

Change b from 2 to 3:
```
<<<< ORIGINAL
a = 1
b = 2
====
a = 1
b = 3
>>>> UPDATED
```

Change "foo" to "bar" in the print statement:
```
<<<< ORIGINAL
class Example:
    def foo(self):
        print("foo")
    def bar(self):
        pass
====
class Example:
    def foo(self):
        print("bar")
    def bar(self):
        pass
>>>> UPDATED
```
[/RESP]

[INST]
I have the following file `src/components/App.tsx` that I would like to modify to complete the task.

```
import {
  ChakraProvider,
  Box,
  extendTheme,
  useColorMode,
  ThemeConfig,
} from "@chakra-ui/react";
import CallToAction from "./components/CallToAction";
import { Helmet } from "react-helmet";
import Navbar from "./components/Navbar";
import Banner from "./components/Banner";
import og_image from "./assets/og_image.png";
import { ColorModeSwitcher } from "./ColorModeSwitcher";
import { useEffect } from "react";
import Testimonials from "./components/Testimonials";
import Users from "./components/Users";
import AboutUs from "./components/AboutUs";
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';

import circles from "./assets/circles.svg";
import Features from "./components/Features";
import Conclusion from "./components/Conclusion";

const config: ThemeConfig = {
  initialColorMode: "dark",
  useSystemColorMode: false,
};

const theme = extendTheme({ config });

function ForceDarkMode(props: { children: JSX.Element }) {
  const { colorMode, toggleColorMode } = useColorMode();

  useEffect(() => {
    if (colorMode === "dark") return;
    toggleColorMode();
  }, [colorMode, toggleColorMode]);

  return props.children;
}
```

Task: Change the following line to use a class component instead of a functional component.
[/INST]

[RESP]
"""

"""
### Response Format

Respond by first thinking step-by-step in the following format:

Step-by-step thoughts: (max 5 thoughts)
* Thought 1
* Thought 2
...

Then indicating which sections you would like to modify and how you would modify them. Write your response in diff hunks. This will be applied to the original file. Write the least amount of diffs possible to complete the task in this format:

Write multiple small diff hunks instead of one large diff hunk. Only provide the lines necessary and do not just copy the whole file.


```diff
line before
- first old code
+ first new code
line after
```


### Instructions

Migrate to class components.


"""

# prompt = """\
# ```
# import {
#   ChakraProvider,
#   Box,
#   extendTheme,
#   useColorMode,
#   ThemeConfig,
# } from "@chakra-ui/react";
# import CallToAction from "./components/CallToAction";
# import { Helmet } from "react-helmet";
# import Navbar from "./components/Navbar";
# import Banner from "./components/Banner";
# import og_image from "./assets/og_image.png";
# import { ColorModeSwitcher } from "./ColorModeSwitcher";
# import { useEffect } from "react";
# import Testimonials from "./components/Testimonials";
# import Users from "./components/Users";
# import AboutUs from "./components/AboutUs";
# import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';

# import circles from "./assets/circles.svg";
# import Features from "./components/Features";
# import Conclusion from "./components/Conclusion";

# const config: ThemeConfig = {
#   initialColorMode: "dark",
#   useSystemColorMode: false,
# };

# const theme = extendTheme({ config });

# function ForceDarkMode(props: { children: JSX.Element }) {
#   const { colorMode, toggleColorMode } = useColorMode();

#   useEffect(() => {
#     if (colorMode === "dark") return;
#     toggleColorMode();
#   }, [colorMode, toggleColorMode]);

#   return props.children;
# }
# ```

# ### Instructions

# Rewrite this to use class components:

# ### Response
# """


stream = client.text_generation(prompt, stream=True, details=True, **gen_kwargs)

print(prompt)
for result in stream:
    # print(result.token)
    if result.token.special:
        continue
    if result.token.text in gen_kwargs["stop_sequences"]:
        break
    print(result.token.text, end="")
    # print(result.token)
