// @ts-nocheck

import { defineConfig } from "cypress";

export default defineConfig({
  projectId: "wf92eh",
  e2e: {
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
    experimentalStudio: true,
    baseUrl: "http://localhost:4000",
    // mbp 15
    viewportHeight: 900,
    viewportWidth: 1440,
  },
});
