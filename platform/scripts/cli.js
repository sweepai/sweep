#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { consola, createConsola } = require("consola");

(async () => {
  const chalk = (await import('chalk')).default;
  const inquirer = (await import('inquirer')).default;

  const packagePath = path.join(__dirname, "..");
  const envLocalPath = path.join(packagePath, ".env.local");

consola.box(`

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
        @@@@@@@@@@@@@@@@@@@@  @@@@@@#            ${chalk.magenta.bold("Sweep AI Assistant")}
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
    const command = process.argv[2] === "build" ? `${process.execPath} ${require.resolve('next/dist/bin/next')} build --no-lint` : `${process.execPath} ${require.resolve('next/dist/bin/next')} start --port 4000`;
    consola.info(`> ${command}\n`);
    const childProcess = spawn("sh", ["-c", command], { cwd: packagePath, stdio: "inherit" });

    // Check the exit code of the process
    childProcess.on('exit', (code, signal) => {
      if (code) {
        consola.error(`If you got a message regarding a missing build, try running \`npx sweepai build\` to rebuild the package.`)
        process.exit(code);
      }
    });
  }
  var envLocal = fs.readFileSync(envLocalPath, "utf8");
  if (!envLocal.includes("OPENAI_API_KEY")) {
    const answers = await inquirer.prompt([
      {
        type: 'password',
        mask: true,
        name: 'openai_api_key',
        message: 'Enter your OpenAI API key (https://platform.openai.com/api-keys):',
      }
    ])
    envLocal += `OPENAI_API_KEY=${answers.openai_api_key}\n`;
    fs.writeFileSync(envLocalPath, envLocal);
  }
  main()
})()
