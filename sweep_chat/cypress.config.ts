import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    baseUrl: 'http://localhost:3000',
    setupNodeEvents(on: Cypress.PluginEvents, config: Cypress.Config) {
      // implement node event listeners here
    },
    viewportWidth: 1536,
    viewportHeight: 960,
  },
})
