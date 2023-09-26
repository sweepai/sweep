# instantiate a modal sandbox
from sweepai.sandbox.src.sandbox_utils import Sandbox
from sweepai.utils.github_utils import get_github_client, get_token

_, g = get_github_client(installation_id=36855882)
installation_id = 36855882
token = get_token(installation_id)
# repo_name = "sweepai/landing-page"
repo_name = "sweepai/sweep"
repo = g.get_repo(repo_name)
sandbox_config = {
    "install": "",
    "formatter": "trunk fmt {file}",
    "linter": "trunk check --fix {file}",
}
repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
sandbox = Sandbox.from_token(repo, repo_url, sandbox_config)
# change a file to have a syntax error
bad_file_contents = """\
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


// @ts-ignore
window.intercomSettings = {
  api_base: "https://api-iam.intercom.io",
  app_id: "ce8fl00z",
  action_color: "#6b46c1",
  background_color: "#342867",
};

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
};"""
file_path = "src/App.tsx"

bad_file_contents = "print(hello"
file_path = "sweepai/api.py"
# run trunk
# run_format(sandbox, bad_file)
# pipe out logs
# import pdb; pdb.set_trace()

# @stub.local_entrypoint()
# def func():
#     print(run_sandbox(sandbox, file_path, bad_file_contents))

# run this command
# modal run -q sandbox/test_sandbox.py::func
