#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

// const currentDir = process.cwd();
// const envLocalPath = path.join(__dirname, ".env.local");
// const targetEnvLocalPath = path.join(sweepaiDir, ".env.local");

// if (fs.existsSync(envLocalPath)) {
//   fs.copyFileSync(envLocalPath, targetEnvLocalPath);
// }

const command = process.argv[2] === "build" ? `${process.execPath} ${require.resolve('next/dist/bin/next')} build` : `${process.execPath} ${require.resolve('next/dist/bin/next')} start --port 3000`;
console.log(`> ${command}`);
const childProcess = spawn("sh", ["-c", command], { cwd: __dirname, stdio: "inherit" });
