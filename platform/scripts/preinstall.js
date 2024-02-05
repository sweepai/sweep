#!/usr/bin/env node

const minNodeVersion = 18;
const currentNodeVersion = parseInt(process.versions.node.split('.')[0], 10);

if (currentNodeVersion < minNodeVersion) {
  console.error(`Requires Node.js version ${minNodeVersion} or higher. Current version: ${process.versions.node}. To update Node.js, run "npm install -g n && n ${minNodeVersion}".`);
  process.exit(1);
}
