#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const currentDir = process.cwd();
const sweepaiDir = path.join(process.cwd(), "node_modules", "sweepai");
const envLocalPath = path.join(process.cwd(), ".env.local");
const targetEnvLocalPath = path.join(sweepaiDir, ".env.local");

if (fs.existsSync(envLocalPath)) {
  fs.copyFileSync(envLocalPath, targetEnvLocalPath);
}

const command =
  process.argv[2] === "build"
    ? `cd ${sweepaiDir} && npm i && next build --no-lint || ${currentDir}`
    : `cd ${sweepaiDir} && next start || cd ${currentDir}`;
const childProcess = spawn("sh", ["-c", command], { cwd: sweepaiDir });

childProcess.stdout.on("data", (data) => {
  console.log(data.toString());
});

childProcess.stderr.on("data", (data) => {
  console.error(data.toString());
});

childProcess.on("exit", (code) => {
  console.log(`Child childProcess exited with code ${code}`);
});
