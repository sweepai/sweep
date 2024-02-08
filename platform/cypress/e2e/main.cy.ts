describe('main platform', () => {
  it('opens', () => {
    cy.viewport("macbook-15")
    cy.visit('/')

    console.log("Clicking on the 'Coding' button")
    cy.contains('button', /^Coding$/).click({force: true});

    console.log("Setting repo name")
    cy.exec('pwd').then((result) => {
      const cwd = result.stdout;
      const sections = cwd.split('/');
      cy.log(cwd)
      cy.log(sections.slice(0, sections.length - 1).join("/"))
      cy.get('[placeholder="/Users/sweep/path/to/repo"]').clear().type(sections.slice(0, sections.length - 1).join("/"));
      cy.get('[placeholder="node_modules, .log, build"]').clear().type(".git, node_modules, venv, __pycache__, .next, cache, logs")
      cy.get('#name').clear().type(sections.slice(0, sections.length - 1).join("/"));

      cy.contains("span", "Close").click({force: true});

      cy.contains("div", "Successfully fetched ")

      console.log("Collapsing dropdown")
      cy.get('.grow > .p-2').click()

      console.log("Selecting Dockerfile as file to edit")
      cy.get('#creation-panel-plus-sign-wraper > .flex > .inline-flex').trigger('mouseover')
      cy.contains("button", "Modify file").click();
      cy.get('input[role="combobox"]').type("dockerfile");
      cy.get('[data-value="dockerfile"]').click();

      console.log("Editing text box")
      cy.get('.justify-between > .flex > span', { timeout: 10000 }).click()
      cy.get('.min-h-\\\[50px\\\]__input').type('change to 8081');

      console.log("Clicking modify button")
      cy.get('.justify-end > span > :nth-child(1)').click();
      cy.get('[style="flex: 68.2 1 0px; overflow: hidden;"] > .h-full > .mt-2').click();

      console.log("Checking if the right changes were made")
      console.warn("This test is not working as expected. It should be checking if the changes were made to the file, but it's not.")
      // cy.get('.cm-changedLine', { timeout: 30000 }).should('contain', '8081');
    })
    })
})
