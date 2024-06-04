const testMessage = "In the vector search logic, how would I migrate the KNN to use HNSW instead?"

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

  it("can stop the chat", () => {
    cy.get('.grow > .flex').type("sweepai/sweep").blur()
    cy.get(':nth-child(5) > .flex', { timeout: 10000 }).should('have.attr', 'placeholder', 'Type a message...')

    cy.get(':nth-child(5) > .flex').type(testMessage + "{enter}")
    cy.wait(1000)
    cy.get(':nth-child(5) > .inline-flex').click()
    cy.wait(3000)
    cy.on('uncaught:exception', (err, runnable) => {
      expect(err.message).to.include('No snippets found');
      return false;
    })
  })

  it("can send a message", () => {
    cy.get('.grow > .flex').type("sweepai/sweep").blur()
    cy.get(':nth-child(5) > .flex', { timeout: 10000 }).should('have.attr', 'placeholder', 'Type a message...')

    cy.get(':nth-child(5) > .flex').type(testMessage + "{enter}")
    cy.get('.justify-end > .transition-color').should("contain.text", testMessage)

    // Validate response from the LLM
    cy.get(':nth-child(3) > .transition-color', { timeout: 30000 }).should("contain.text", "Analysis")
  })
})