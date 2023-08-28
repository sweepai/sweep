# # Hosting any LLaMA 2 model with Text Generation Inference (TGI)
#
# In this example, we show how to run an optimized inference server using [Text Generation Inference (TGI)](https://github.com/huggingface/text-generation-inference)
# with performance advantages over standard text generation pipelines including:
# - continuous batching, so multiple generations can take place at the same time on a single container
# - PagedAttention, an optimization that increases throughput.
#
# This example deployment, [accessible here](https://modal-labs--tgi-app.modal.run), can serve LLaMA 2 70B with
# 70 second cold starts, up to 200 tokens/s of throughput and per-token latency of 55ms.

# ## Setup
#
# First we import the components we need from `modal`.

from pathlib import Path

from modal import Image, Mount, Secret, Stub, Volume, asgi_app, gpu, method

# Next, we set which model to serve, taking care to specify the number of GPUs required
# to fit the model into VRAM, and the quantization method (`bitsandbytes` or `gptq`) if desired.
# Note that quantization does degrade token generation performance significantly.
#
# Any model supported by TGI can be chosen here.

N_GPUS = 4
# MODEL_ID = "meta-llama/Llama-2-70b-chat-hf"
# MODEL_ID = "codellama/CodeLlama-34b-Instruct-hf"
MODEL_ID = "WizardLM/WizardCoder-Python-34B-V1.0"
# MODEL_ID = "replit/replit-code-v1-3b"
# MODEL_ID = "Phind/Phind-CodeLlama-34B-v1"
# Add `["--quantize", "gptq"]` for TheBloke GPTQ models.

MAX_CONTEXT = 8192
INITIAL_CONTEXT = 2048
LAUNCH_FLAGS = [
    "--model-id",
    MODEL_ID,
    "--rope-scaling",
    "dynamic",
    "--max-input-length",
    str(MAX_CONTEXT),
    "--max-batch-prefill-tokens",
    str(MAX_CONTEXT),
    "--rope-factor",
    str(MAX_CONTEXT / INITIAL_CONTEXT),
    "--max-total-tokens",
    str(MAX_CONTEXT * 2),
]

# ## Define a container image
#
# We want to create a Modal image which has the Huggingface model cache pre-populated.
# The benefit of this is that the container no longer has to re-download the model from Huggingface -
# instead, it will take advantage of Modal's internal filesystem for faster cold starts. On
# the largest 70B model, the 135GB model can be loaded in as little as 70 seconds.
#
# ### Download the weights
# Since TGI uses `snapshot_download` under the hood, running this function for our image build
# will place the weights into the cache directly. There are no progress bars as this uses
# the high-throughput `hf-transfer` library, but expect ~700MB/s for this step.
#


# def download_model():
# import subprocess

# subprocess.run(["text-generation-server", "download-weights", MODEL_ID])


# ### Image definition
# We’ll start from a Dockerhub image recommended by TGI, and override the default `ENTRYPOINT` for
# Modal to run its own which enables seamless serverless deployments.
#
# Next we run the download step to pre-populate the image with our model weights.
#
# For this step to work on a gated model such as LLaMA 2, the HUGGING_FACE_HUB_TOKEN environment
# variable must be set ([reference](https://github.com/huggingface/text-generation-inference#using-a-private-or-gated-model)).
# After [creating a HuggingFace access token](https://huggingface.co/settings/tokens),
# head to the [secrets page](https://modal.com/secrets) to create a Modal secret.
#
# The key should be `HUGGING_FACE_HUB_TOKEN` and the value should be your access token.
#
# Finally, we install the `text-generation` client to interface with TGI's Rust webserver over `localhost`.

image = (
    Image.from_dockerhub(
        "ghcr.io/huggingface/text-generation-inference:1.0.1"
    ).dockerfile_commands("ENTRYPOINT []")
    # .run_function(download_model, secret=Secret.from_name("huggingface"))
    .pip_install("text-generation")
)

stub = Stub("example-tgi-" + MODEL_ID.split("/")[-1], image=image)
stub.volume = Volume.persisted("test-model-cache")

# ## The model class
#
# The inference function is best represented with Modal's [class syntax](/docs/guide/lifecycle-functions).
# The class syntax is a special representation for a Modal function which splits logic into two parts:
# 1. the `__enter__` method, which runs once per container when it starts up, and
# 2. the `@method()` function, which runs per inference request.
#
# This means the model is loaded into the GPUs, and the backend for TGI is launched just once when each
# container starts, and this state is cached for each subsequent invocation of the function.
# Note that on start-up, we must wait for the Rust webserver to accept connections before considering the
# container ready.
#
# Here, we also
# - specify the secret so the `HUGGING_FACE_HUB_TOKEN` environment variable is set
# - specify how many A100s we need per container
# - specify that each container is allowed to handle up to 10 inputs (i.e. requests) simultaneously
# - keep idle containers for 10 minutes before spinning down
# - lift the timeout of each request.


@stub.cls(
    secret=Secret.from_name("huggingface"),
    gpu=gpu.A100(count=N_GPUS),
    allow_concurrent_inputs=10,
    container_idle_timeout=60 * 10,
    timeout=60 * 60,
    concurrency_limit=1,
    volumes={
        "/data": stub.volume,
    },
    keep_warm=1,
)
class Model:
    def __enter__(self):
        import socket
        import subprocess
        import time

        from text_generation import AsyncClient

        subprocess.run(["rm", "-rf", "/data/*"])
        subprocess.run(["text-generation-server", "download-weights", MODEL_ID])
        stub.volume.commit()
        stub.volume.reload()
        print("Running ls /data")
        process = subprocess.run("ls /data", shell=True, capture_output=True)
        print(process.stdout.decode())
        self.launcher = subprocess.Popen(["text-generation-launcher"] + LAUNCH_FLAGS)
        self.client = AsyncClient("http://0.0.0.0:80", timeout=60)
        #         self.template = """<s>[INST] <<SYS>>
        # {system}
        # <</SYS>>

        # {user} [/INST] """

        # Poll until webserver at 0.0.0.0:80 accepts connections before running inputs.
        def webserver_ready():
            try:
                socket.create_connection(("0.0.0.0", 80), timeout=1).close()
                return True
            except (socket.timeout, ConnectionRefusedError):
                return False

        while not webserver_ready():
            time.sleep(1.0)

        stub.volume.commit()
        print("Webserver ready!")

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.launcher.terminate()

    @method()
    async def generate(self, question: str, max_tokens: int = 1024):
        # prompt = self.template.format(system="", user=question)
        prompt = question
        result = await self.client.generate(
            prompt, max_new_tokens=max_tokens, temperature=0.01
        )

        return result.generated_text

    @method()
    async def generate_stream(self, question: str):
        # prompt = self.template.format(system="", user=question)
        prompt = question

        async for response in self.client.generate_stream(prompt, max_new_tokens=1024):
            print(response)
            if not response.token.special:
                yield response.token.text


context = """
[INST]
<relevant_snippets_in_repo>
<snippet source="src/components/CallToAction.tsx:1-114">
1:   Flex,
2:   Container,
3:   Heading,
4:   Stack,
5:   Text,
6:   Button,
7: } from "@chakra-ui/react";
8: import { tsParticles } from "tsparticles";
9: import { loadConfettiPreset } from "tsparticles-preset-confetti";
10: import { FaDiscord, FaGithub } from "react-icons/fa";
11: import { useState } from "react";
12: import logo from "../assets/icon.png";
13:
14: import ExternalLinkWithText from "./ExternalLinkWithText";
15: const demo = require("../assets/demo.mp4");
16:
17: export default function CallToAction() {
18:   const [spin, setSpin] = useState(false);
19:   // const canvas = document.getElementById('canvas3d');
20:   // const app = new Application(canvas);
21:   // app.load('https://prod.spline.design/jzV1MbbHCyCmMG7u/scene.splinecode');
22:   return (
23:     <Container maxW={"5xl"}>
24:       <Stack
25:         textAlign={"center"}
26:         align={"center"}
27:         spacing={{ base: 8, md: 10 }}
28:         py={{ base: 4, md: 15 }}
29:         style={{ paddingTop: "0 !important" }}
30:         mb={36}
31:       >
32:         <img src={logo} alt="Logo" style={{ width: '200px', animation: spin ? "spin 0.5s linear" : "bob 0.75s ease-in-out infinite alternate", marginTop: "-2rem !important", borderRadius: "50%" }} onClick={async () => {
33:             setSpin(!spin);
34:             await loadConfettiPreset(tsParticles);
35:             await tsParticles.load("tsparticles", {
36:               preset: "confetti",
37:               particles: {
38:                 color: {
39:                   value: ["#800080", "#FFFFFF"],
40:                 },
41:               },
42:             });
43:           }} />
44:         {/* <img src={logo} alt="Logo" width={120} height={120} style={{
45:           animation: "bob 0.75s ease-in-out infinite alternate",
46:         }} /> */}
47:         <style>
48:           {`
49:             @keyframes bob {
50:               from {
51:                 transform: translateY(0);
52:               }
53:               to {
54:                 transform: translateY(15px);
55:               }
56:             }
57:             @keyframes spin {
58:               from {
59:                 transform: rotate(0deg) scale(1);
60:               }
61:               to {
62:                 transform: rotate(360deg);
63:               }
64:             }
65:           `}
66:         </style>
67:         <Heading
68:           fontWeight={600}
69:           fontSize={{ base: "3xl", sm: "4xl", md: "6xl" }}
70:           lineHeight={"110%"}
71:           mt="0 !important"
72:         >
73:           Ship code faster
74:         </Heading>
75:         <Text color={"purple.400"} maxW={"3xl"} mt="1rem !important" mb="1rem !important">
76:           Let Sweep handle your tech debt so you can focus on the exciting problems
77:         </Text>
78:         <Button
79:           color="white"
80:           p={6}
81:           colorScheme={"purple"}
82:           bg={"purple.400"}
83:           _hover={{ bg: "purple.600" }}
84:           onClick={() => window.open("https://github.com/apps/sweep-ai")}
85:           fontSize={"xl"}
86:           mb="1rem !important"
87:         >
88:           <FaGithub />&nbsp;&nbsp;Install Sweep
89:         </Button>
90:         <ExternalLinkWithText
91:           href="https://discord.gg/sweep" // updated link
92:           color="purple.400"
93:           mt="0 !important"
94:           style={{
95:             display: "flex",
96:             flexDirection: "row",
97:             alignItems: "center",
98:           }}
99:         >
100:           <FaDiscord />&nbsp;&nbsp;Join our Discord
101:         </ExternalLinkWithText>
102:         <Flex w={"full"} mt="4rem !important">
103:           <Container width="100vw" boxShadow="0 0 80px #181818" p={0} maxWidth="full">
104:             <video src={demo} autoPlay muted loop playsInline>
105:               Your browser does not support the video tag.
106:             </video>
107:           </Container>
108:         </Flex>
109:       </Stack>
110:     </Container>
111:   );
112: };
</snippet>
<snippet source="src/App.tsx:1-106">
1:   ChakraProvider,
2:   Box,
3:   extendTheme,
4:   useColorMode,
5:   ThemeConfig,
6: } from "@chakra-ui/react";
7: import CallToAction from "./components/CallToAction";
8: import { Helmet } from "react-helmet";
9: import Navbar from "./components/Navbar";
10: import Banner from "./components/Banner";
11: import og_image from "./assets/og_image.png";
12: import { ColorModeSwitcher } from "./ColorModeSwitcher";
13: import { useEffect } from "react";
14: import Testimonials from "./components/Testimonials";
15: import Users from "./components/Users";
16: import AboutUs from "./components/AboutUs";
17: import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
18:
19: import circles from "./assets/circles.svg";
20: import Features from "./components/Features";
21: import Conclusion from "./components/Conclusion";
22:
23: const config: ThemeConfig = {
24:   initialColorMode: "dark",
25:   useSystemColorMode: false,
26: };
27:
28: const theme = extendTheme({ config });
29:
30: function ForceDarkMode(props: { children: JSX.Element }) {
31:   const { colorMode, toggleColorMode } = useColorMode();
32:
33:   useEffect(() => {
34:     if (colorMode === "dark") return;
35:     toggleColorMode();
36:   }, [colorMode, toggleColorMode]);
37:
38:   return props.children;
39: }
40:
41:
42: // @ts-ignore
43: window.intercomSettings = {
44:   api_base: "https://api-iam.intercom.io",
45:   app_id: "ce8fl00z",
46:   action_color: "#6b46c1",
47:   background_color: "#342867",
48: };
49:
50: export const App = () => {
51:   useEffect(() => {
52:     const script = document.createElement("script");
53:     script.type = "text/javascript";
54:     script.async = true;
55:     script.innerHTML = `(function(){var w=window;var ic=w.Intercom;if(typeof ic==="function"){ic('reattach_activator');ic('update',w.intercomSettings);}else{var d=document;var i=function(){i.c(arguments);};i.q=[];i.c=function(args){i.q.push(args);};w.Intercom=i;var l=function(){var s=d.createElement('script');s.type='text/javascript';s.async=true;s.src='https://widget.intercom.io/widget/ce8fl00z';var x=d.getElementsByTagName('script')[0];x.parentNode.insertBefore(s,x);};if(document.readyState==='complete'){l();}else if(w.attachEvent){w.attachEvent('onload',l);}else{w.addEventListener('load',l,false);}}})();`;
56:     document.body.appendChild(script);
57:   }, []);
58:   return (
59:     <>
60:       <Helmet>
61:         <meta property="og:image" content={og_image} />
62:         <link rel="icon" type="image/png" sizes="16x16" href="/final-sweep-wizard_16x16.png" />
63:         <link rel="icon" type="image/png" sizes="32x32" href="/final-sweep-wizard_32x32.png" />
64:         <link rel="icon" type="image/png" sizes="48x48" href="/final-sweep-wizard_48x48.png" />
65:         <link rel="icon" type="image/png" sizes="64x64" href="/final-sweep-wizard_64x64.png" />
66:         <link rel="icon" type="image/png" sizes="128x128" href="/final-sweep-wizard_128x128.png" />
67:         <link rel="icon" type="image/png" sizes="256x256" href="/final-sweep-wizard_256x256.png" />
68:       </Helmet>
69:       <ChakraProvider theme={theme}>
70:         <ForceDarkMode>
71:           <Box
72:             textAlign="center"
73:             fontSize="xl"
74:             bgColor="#0d0a1a"
75:             bgImage={circles}
76:             bgPos="0 0"
77:             bgSize="100%"
78:             minH="100vh"
79:             bgRepeat="no-repeat"
80:             overflowX="hidden"
81:           >
82:             {false && <ColorModeSwitcher />}
83:             <Banner />
84:             <Router>
85:               <Navbar />
86:               <Switch>
87:                 <Route exact path="/">
88:                   <CallToAction />
89:                   <Users />
90:                   <Features />
91:                   <Testimonials />
92:                   <Conclusion />
93:                 </Route>
94:                 <Route path="/about-us">
95:                   <AboutUs />
96:                 </Route>
97:               </Switch>
98:             </Router>
99:           </Box>
100:         </ForceDarkMode>
101:       </ChakraProvider>
102:     </>
103:   );
104: };
</snippet>
<snippet source="src/test-utils.tsx:1-13">
1: import { render, RenderOptions } from "@testing-library/react"
2: import { ChakraProvider, theme } from "@chakra-ui/react"
3:
4: const AllProviders = ({ children }: { children?: React.ReactNode }) => (
5:   <ChakraProvider theme={theme}>{children}</ChakraProvider>
6: )
7:
8: const customRender = (ui: React.ReactElement, options?: RenderOptions) =>
9:   render(ui, { wrapper: AllProviders, ...options })
10:
11: export { customRender as render }
</snippet>
<snippet source="src/reportWebVitals.ts:1-16">
1:
2: const reportWebVitals = (onPerfEntry?: ReportHandler) => {
3:   if (onPerfEntry && onPerfEntry instanceof Function) {
4:     import("web-vitals").then(({ getCLS, getFID, getFCP, getLCP, getTTFB }) => {
5:       getCLS(onPerfEntry)
6:       getFID(onPerfEntry)
7:       getFCP(onPerfEntry)
8:       getLCP(onPerfEntry)
9:       getTTFB(onPerfEntry)
10:     })
11:   }
12: }
13:
14: export default reportWebVitals
</snippet>
<snippet source="src/components/Features.tsx:1-129">
1: import { FaBook, FaGithub, FaSlack } from "react-icons/fa";
2: import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'; // @ts-ignore
3: import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
4:
5: import GHAIcon from "../assets/gha.svg";
6:
7: import logo from "../assets/icon.png";
8: import pills_examples from "../assets/pills_examples.svg";
9: import User from "./User";
10:
11: const example_code = `import os
12: import tempfile
13: from git import Repo
14: ...
15: try:
16:     repo_dir = os.path.join(tempfile.gettempdir(), repo_full_name)
17:     if os.path.exists(repo_dir):
18:         git_repo = Repo(repo_dir)
19:         git_repo.remotes.origin.pull()
20:     else:
21:         Repo.clone_from(repo_url, repo_dir)
22: `;
23:
24: const example_diff_code_prefix = `def deactivate(self, plugin_name: str):
25:     '''
26:     Deactivates an activate plugin.
27:     '''
28:     if plugin_name not in self.active_plugins:
29:         del self.active_plugins[plugin_name]
30: `;
31:
32: const example_gha_log = `Error: Module '"tsparticles"' has no exported member 'loadConfettiPreset'.
33: Error: Property 'style' does not exist on type 'EventTarget'.`;
34:
35: const example_diff_code_gha = `import { Flex, Container, Heading, Stack, Text, Button } from "@chakra-ui/react";
36: - import { loadConfettiPreset, tsParticles } from "tsparticles";
37: + import { tsParticles } from "tsparticles";
38: import { FaDiscord, FaGithub } from "react-icons/fa";
39: import Spline from '@splinetool/react-spline';
40: ...
41:         await tsParticles.load("tsparticles", {
42:             preset: "confetti",
43:             particles: {
44:             color: {
45:                 value: ["#0000ff", "#00ff00"],
46:             },
47:             },
48:         });
49: -       target.style.transform = "rotate(360deg)";
50: +       (target as HTMLElement).style.transform = "rotate(360deg)";
51:     }}
52: ...
53: `;
54:
55: const example_diff_code_diff = `-       self.prompt = self.fill_prompt(self.template)
56: -       self.tokens = count_tokens(self.prompt)
57: +       self.tokens = count_tokens(self.get_prompt())
58: `;
59:
60: const customStyle = {
61:     ...oneDark,
62:     'code[class*="language-"]': {
63:         ...oneDark['code[class*="language-"]'],
64:         background: 'transparent',
65:     },
66: };
67:
68: const Dialog = ({ children, user, userProps, ...props }: any) => {
69:     return (
70:         <HStack alignItems="flex-start" spacing={6} maxW="100% !important">
71:             <User {...userProps}>{user}</User>
72:             <Box borderRadius="10px" display="flex" justifyContent="center" alignItems="center" color="purple.300" borderColor="purple.300" borderWidth="1px" p={4} {...props}>
73:                 {children}
74:             </Box>
75:         </HStack>
76:     )
77: }
78:
79: const GithubDialog = ({ children, user, userProps, ...props }: any) => {
80:     return (
81:         <HStack alignItems="flex-start" spacing={6} maxW="100% !important" w="100% !important">
82:             <User {...userProps}>{user}</User>
83:             <Box borderRadius="10px" display="flex" justifyContent="center" alignItems="center" color="white.900" borderColor="purple.300" borderWidth="1px" p={4} {...props}>
84:                 {children}
85:             </Box>
86:         </HStack>
87:     )
88: }
89:
90: export default function Features() {
91:     return (
92:         <>
93:             <Box display="flex" justifyContent="center" alignItems="center" mb={96}>
94:                 <Box m={8} display="flex" flexWrap="wrap" justifyContent="space-between" w="80%" textAlign="left">
95:                     <Flex width={{ base: "100%", md: "45%" }} textAlign="left" justifyContent="center" alignItems="center" mb={12}>
96:                         <Box>
97:                             <img src={logo} alt="Sweep logo" width={50} />
98:                             <Text mt={4} fontSize="2xl" fontWeight="bold">Clean up your tech debt, automatically</Text>
99:                             <Text mt={4} fontSize="md" color="lightgrey">Sweep generates repository-level code at your command. Cut down your dev time on mundane tasks, like tests, documentation, and refactoring.</Text>
100:                         </Box>
101:                     </Flex>
102:                     <Box width={{ base: "100%", md: "45%" }} maxW="100%">
103:                         <VStack alignItems="flex-start" spacing={6}>
104:                             <Dialog
105:                                 user={<Text fontSize="md" color="white">KL</Text>}
106:                                 userProps={{ bgColor: "purple.900", p: 2, borderWidth: 2 }}
107:                                 bgColor="purple.900"
108:                                 borderWidth={2}
109:                             >
110:                                 <Text fontSize="md" color="white">
111:                                     Sweep: Use OS Agnostic Temp Directory
112:                                 </Text>
113:                             </Dialog>
114:                             <Dialog user={<img src={logo} alt="Sweep logo" />}>
115:                                 <Text
116:                                     position="relative"
117:                                     fontSize="md"
118:                                     color="white"
119:                                 >
120:                                     <Box
121:                                         position="absolute"
122:                                         bottom={0}
123:                                         left={0}
124:                                         right={0}
125:                                         height="100%"
126:                                         background={`linear-gradient(to bottom, transparent, #0d0a1aaa)`}
127:                                     />
128:                                     This PR addresses issue #367, which pointed out that the current implementation of the temporary directory in sweepai/app/ui.py is not compatible with Windows.
...
</snippet>
</relevant_snippets_in_repo>

<relevant_paths_in_repo>
src/components/CallToAction.tsx
src/App.tsx
src/test-utils.tsx
src/reportWebVitals.ts
src/components/Features.tsx
</relevant_paths_in_repo>

<repo_tree>
.github/...
.gitignore
.vscode/...
README.md
package.json
public/...
src/
  App.test.tsx
  App.tsx
  ColorModeSwitcher.tsx
  assets/...
  src/components/
    AboutUs.tsx
    Banner.tsx
    CallToAction.tsx
    Conclusion.tsx
    Examples.tsx
    ExternalLinkWithText.tsx
    Features.tsx
    Footer.tsx
    Navbar.tsx
    PricingModal.tsx
    Testimonials.tsx
    User.tsx
    Users.tsx
  index.tsx
  logo.svg
  react-app-env.d.ts
  reportWebVitals.ts
  serviceWorker.ts
  setupTests.ts
  test-utils.tsx
sweep.yaml
tsconfig.json
yarn.lock
</repo_tree>

### Request ###

# Repo & Issue Metadata
Repo: landing-page: No description provided.
Issue Url: https://github.com/sweepai/landing-page/issues/366
Username: kevinlu1248
Issue Title: Refactor App, ColorModeSwitcher, and AboutUs to class components
Issue Description:
* In src/App.tsx, refactor the App function into a class component.
* In src/ColorModeSwitcher.tsx, refactor the ColorModeSwitcher function into a class component.
* In src/components/AboutUs.tsx, refactor the AboutUs function into a class component.

### Instructions ###

Think step-by-step to break down the requested problem or feature, and then figure out what to change in the current codebase.
Then, provide a list of files you would like to modify, abiding by the following:
* You may only create, modify, delete and rename files
* Including the FULL path, e.g. src/main.py and not just main.py, using the repo_tree as the source of truth
* ALWAYS prefer modifying existing files over creating new files
* Only modify or create files that DEFINITELY need to be touched
* Use detailed, natural language instructions on what to modify regarding business logic, and do not add low-level details like imports
* Be concrete with instructions and do not write "check for x" or "ensure y is done". Simply write "add x" or "change y to z".
* Create/modify up to 5 FILES
* Do not modify non-text files such as images, svgs, binary, etc

### Format ###

You MUST follow the following format with the final output in XML tags:

Root cause:
Write an abstract minimum plan to address this issue in the least amount of change possible. Try to originate the root causes of this issue. Be clear and concise. 1 paragraph.

Step-by-step thoughts with explanations:
* Thought 1
* Thought 2
...

<plan>
<create file="file_path_1">
* Instruction 1 for file_path_1
* Instruction 2 for file_path_1
...
</create>

<create file="file_path_2">
* Instruction 1 for file_path_2
* Instruction 2 for file_path_2
...
</create>

...

<modify file="file_path_3">
* Instruction 1 for file_path_3
* Instruction 2 for file_path_3
...
</modify>

<modify file="file_path_4">
* Instruction 1 for file_path_4
* Instruction 2 for file_path_4
...
</modify>

...

<delete file="file_path_5"></delete>

...

<rename file="file_path_6">new full path for file path 6</rename>

...
</plan>
[/INST]

[SOLUTION]"""


# ## Run the model
# We define a [`local_entrypoint`](/docs/guide/apps#entrypoints-for-ephemeral-apps) to invoke
# our remote function. You can run this script locally with `modal run text_generation_inference.py`.
@stub.local_entrypoint()
def main():
    print(
        Model().generate.remote(
            context  # "Implement a Python function to compute the Fibonacci numbers."
        )
    )


# # ## Serve the model
# # Once we deploy this model with `modal deploy text_generation_inference.py`, we can serve it
# # behind an ASGI app front-end. The front-end code (a single file of Alpine.js) is available
# # [here](https://github.com/modal-labs/modal-examples/blob/main/06_gpu_and_ml/llm-frontend/index.html).
# #
# # You can try our deployment [here](https://modal-labs--example-falcon-gptq-get.modal.run/?question=Why%20are%20manhole%20covers%20round?).

# frontend_path = Path(__file__).parent / "llm-frontend"


# @stub.function(
#     mounts=[Mount.from_local_dir(frontend_path, remote_path="/assets")],
#     keep_warm=1,
#     allow_concurrent_inputs=10,
#     timeout=60 * 10,
# )
# @asgi_app(label="tgi-app")
# def app():
#     import json

#     import fastapi
#     import fastapi.staticfiles
#     from fastapi.responses import StreamingResponse

#     web_app = fastapi.FastAPI()

#     @web_app.get("/stats")
#     def stats():
#         stats = Model().generate_stream.get_current_stats()
#         return {
#             "backlog": stats.backlog,
#             "num_total_runners": stats.num_total_runners,
#         }

#     @web_app.get("/completion/{question}")
#     def completion(question: str):
#         from urllib.parse import unquote

#         def generate():
#             for text in Model().generate_stream.remote_gen(unquote(question)):
#                 yield f"data: {json.dumps(dict(text=text), ensure_ascii=False)}\n\n"

#         return StreamingResponse(generate(), media_type="text/event-stream")

#     web_app.mount("/", fastapi.staticfiles.StaticFiles(directory="/assets", html=True))
#     return web_app


# # ## Invoke the model from other apps
# # Once the model is deployed, we can invoke inference from other apps, sharing the same pool
# # of GPU containers with all other apps we might need.
# #
# # ```
# # $ python
# # >>> import modal
# # >>> f = modal.Function.lookup("example-tgi-Llama-2-70b-chat-hf", "Model.generate")
# # >>> f.remote("What is the story about the fox and grapes?")
# # 'The story about the fox and grapes ...
# # ```
# #
