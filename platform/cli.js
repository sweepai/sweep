#!/usr/bin/env node

const { spawn } = require('child_process');

const process = spawn('sh', ['-c', 'next start']);

process.stdout.on('data', (data) => {
    console.log(data.toString());
});

process.stderr.on('data', (data) => {
    console.error(data.toString());
});

process.on('exit', (code) => {
    console.log(`Child process exited with code ${code}`);
});
