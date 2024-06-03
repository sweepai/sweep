describe('sweep chat', () => {
  beforeEach(() => {
    cy.login();
    cy.visit("/")
  });

  it("should provide a valid session", () => {
    cy.get('.h-screen > .justify-between > .flex > .inline-flex').should('exist').and('have.text', 'Sign Out')
  });

  it("can set a repo", () => {
    cy.get('.grow > .flex').type("sweepai/sweep").blur()
    cy.get(':nth-child(5) > .flex', { timeout: 10000 }).should('have.attr', 'placeholder', 'Type a message...')
  })

  it.skip("can send a message", () => {
    cy.get('.grow > .flex').type("sweepai/sweep").blur()
    cy.get(':nth-child(5) > .flex', { timeout: 10000 }).should('have.attr', 'placeholder', 'Type a message...')

    const testMessage = "In the vector search logic, how do I migrate the KNN to use HNSW instead?"
    cy.get(':nth-child(5) > .flex').type(testMessage + "{enter}")
    cy.get('.justify-end > .transition-color').should("contain.text", testMessage)

    // Validate response from the LLM
    cy.get(':nth-child(3) > .transition-color', { timeout: 30000 }).should("contain.text", "Analysis")
  })
})