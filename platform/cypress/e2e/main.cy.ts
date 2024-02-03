describe('main platform', () => {
  it('opens', () => {
    cy.viewport("macbook-15")
    cy.visit('/')

    console.log("Setting repo name")
    cy.exec('pwd').then((result) => {
      cy.get('.flex-col > :nth-child(1) > .flex-row > .inline-flex').then($el => {
        if ($el && $el.is(':contains("Expand")')) {
          $el.click();
        }
      }).then(() => {
        const cwd = result.stdout;
        const sections = cwd.split('/');
        cy.log(cwd)
        cy.log(sections.slice(0, sections.length - 1).join("/"))
        cy.get('[placeholder="node_modules, .log, build"]').clear().type(".git, node_modules, venv, __pycache__, .next, cache, logs")
        cy.get('#name').clear().type(sections.slice(0, sections.length - 1).join("/"));

        console.log("Collapsing dropdown")
        cy.get('.grow > .p-2').click()
        cy.contains('.flex-col > :nth-child(1) > .flex > .inline-flex', 'Expand');

        // console.log("Setting branch")
        // cy.get('.grow > .p-2').click();
        // cy.get('[placeholder="your-branch-here"]').should('not.have.value', "")

        // cy.get("body > main > div > div.p-6 > div > div:nth-child(1) > div.flex.flex-row.justify-between.items-center.mb-2 > button").click();

        console.log("Selecting Dockerfile as file to edit")
        cy.get('.grow > :nth-child(1) > .flex > .inline-flex').first().click()
        cy.get('input[role="combobox"]').clear();
        cy.get('input[role="combobox"]').type('dockerfile');
        cy.get('[data-value="dockerfile"]').click();

        console.log("Editing text box")
        cy.get('.justify-between > .flex > span', { timeout: 10000 }).click()
        cy.get('.min-h-\\\[50px\\\]__input').type('change to 8081');

        console.log("Clicking modify button")
        cy.get('.justify-end > span > :nth-child(1)').click();
        cy.get('[style="flex: 68.2 1 0px; overflow: hidden;"] > .h-full > .mt-2').click();

        console.log("Checking if the right changes were made")
        cy.get('.cm-changedLine', { timeout: 20000 }).should('contain', '8081');
      });
    })
    })
})
