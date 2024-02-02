describe('main platform', () => {
  it('opens', () => {
    cy.viewport("macbook-15")
    cy.visit('/')

    console.log("Setting repo name")
    cy.exec('pwd').then((result) => {
      const cwd = result.stdout;
      const sections = cwd.split('/');
      cy.log(cwd)
      cy.get('#name').type(sections.slice(0, sections.length - 1).join("/"));

      console.log("Setting branch")
      cy.get('.grow > .p-2').click();
      // cy.get('[placeholder="your-branch-here"]').should('not.have.value', "")

      console.log("Collapsing dropdown")
      cy.get("body > main > div > div.p-6 > div > div:nth-child(1) > div.flex.flex-row.justify-between.items-center.mb-2 > button").click();

      console.log("Selecting Dockerfile as file to edit")
      cy.get('.grow > :nth-child(1) > .flex > .inline-flex').click()
      cy.get('input[role="combobox"]').clear();
      cy.get('input[role="combobox"]').type('dockerfile');
      cy.get('[data-value="dockerfile"]').click();

      console.log("Editing text box")
      cy.get('.justify-between > .flex > span').click()
      cy.get('.min-h-\\\[50px\\\]__input').type('change to 8081');

      console.log("Clicking modify button")
      cy.get('.justify-end > span > :nth-child(1)').click();
      cy.get('[style="flex: 68.2 1 0px; overflow: hidden;"] > .h-full > .mt-2').click();

      console.log("Checking if the right changes were made")
      cy.get('.cm-changedLine', { timeout: 20000 }).should('contain', '8081');
    })
    })
})
