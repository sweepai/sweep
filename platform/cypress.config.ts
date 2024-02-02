import { defineConfig } from "cypress";

export default defineConfig({
  e2e: {
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
    experimentalStudio: true,
    baseUrl: 'http://localhost:3000',
    // mbp 15
    viewportHeight: 900,
    viewportWidth: 1440,
  },
});
