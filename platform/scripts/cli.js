#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const readline = require('readline').createInterface({
  input: process.stdin,
  output: process.stdout
});

const envLocalPath = path.join(__dirname, ".env.local");

console.log(`

                    @@@@@@@@@@@@@@@@@@@%*
                #@@@                    @+
              @@                       @
            =@             @@@       @@
          @@              @  @=   @-
          @               @@ @*   @
          @                +@ @%   @
          %@               *@ @=   @@
          @@@@@            =% %  @@
        @@@@@@@@@@@@@@@@@@@  @@@@@
        @@@@@@@@@@@@@@@@@@@  @@@@@@
        @@@@@@@@@@@@@@@@@@@@  @@@@@@#            Sweep AI Assistant
        @@@   %@@@   @@@@@@  @@@@@@@@@
        @@@    @@%   *@@@@# @@@@@@@@@@@@@@
        @@@   @@@@   @@@@@ @@@@@@@@@@@@@@
        @@@@@@@@@@@@@@@@@  @@@@@@@@@@@@@         https://docs.sweep.dev/assistant
        @@@@@@@@@@@@@@@@  @@@@@@@@@@@@
          @@@@@@@@@@@@@@  @@@@@@@@@@@@
          #@@@@@@@@@@@    @@@@@@@@@@
              @@@@@@@    @@@@@@@@@*
                @*    @@@@@@@@
      @%*@@@@@@@       %
      #@               #@
        @            @ @@
        @@         @# @*
          @@*      @  @
            %@@@# @@  @
                %@@@@@

`)

if (!fs.existsSync(envLocalPath)) {
  fs.writeFileSync(envLocalPath, `NEXT_PUBLIC_DEFAULT_REPO_PATH=${process.cwd()}\n`);
}

const main = () => {
  const command = process.argv[2] === "build" ? `${process.execPath} ${require.resolve('next/dist/bin/next')} build --no-lint` : `${process.execPath} ${require.resolve('next/dist/bin/next')} start --port 3000`;
  console.log(`> ${command}\n`);
  const childProcess = spawn("sh", ["-c", command], { cwd: __dirname, stdio: "inherit" });

  // Check the exit code of the process
  childProcess.on('exit', (code, signal) => {
    if (code) {
      console.error(`If you got a message regarding a missing build, try running \`npx sweepai build\` to rebuild the package.`)
      process.exit(code);
    }
  });
}

var envLocal = fs.readFileSync(envLocalPath, "utf8");
if (!envLocal.includes("OPENAI_API_KEY")) {
  readline.question('Enter your OpenAI API key (https://platform.openai.com/api-keys): ', name => {
    envLocal += `OPENAI_API_KEY=${name}\n`;
    fs.writeFileSync(envLocalPath, envLocal);
    readline.close();
    main()
  });
} else {
  main()
}
