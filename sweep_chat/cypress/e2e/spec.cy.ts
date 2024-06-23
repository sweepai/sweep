const testMessage =
  'In the vector search logic, how would I migrate the KNN to use HNSW instead?'
const testPullRequestMessage =
  'Help me review this PR: https://github.com/sweepai/sweep/pull/3978'

const messageInputSelector = '.pl-4 > div.flex > .flex'

describe('sweep chat', () => {
  beforeEach(() => {
    cy.login()
    cy.visit('/')
  })

  it('should provide a valid session', () => {
    cy.get('.rounded-full').click()
    cy.get('div:nth-child(4)').contains('Sign Out')
  })

  it('can set a repo', () => {
    cy.get('[tabindex="-1"] > :nth-child(2) > .items-center > input')
      .type('sweepai/sweep')
      .blur()
    cy.get(messageInputSelector, { timeout: 10000 }).should(
      'have.attr',
      'placeholder',
      'Type a message...'
    )
  })

  it('can stop the chat', () => {
    cy.get('[tabindex="-1"] > :nth-child(2) > .items-center > input')
      .type('sweepai/sweep')
      .blur()
    cy.get(messageInputSelector, { timeout: 10000 }).should(
      'have.attr',
      'placeholder',
      'Type a message...'
    )

    cy.get(messageInputSelector).type(testMessage + '{enter}')
    cy.wait(1000)
    cy.get('.bg-destructive').click()
    cy.on('uncaught:exception', (err, runnable) => {
      expect(err.message).to.include('No snippets found')
      return false
    })
  })

  it('can preview pull requests', () => {
    cy.get('[tabindex="-1"] > :nth-child(2) > .items-center > input')
      .type('sweepai/sweep')
      .blur()
    cy.get(messageInputSelector, { timeout: 10000 }).should(
      'have.attr',
      'placeholder',
      'Type a message...'
    )

    cy.get(messageInputSelector).type(testPullRequestMessage + '{enter}')
    cy.get('a > .bg-zinc-800').contains('Minor ticket utils fix')
  })

  it('can send a message', () => {
    cy.get('[tabindex="-1"] > :nth-child(2) > .items-center > input')
      .type('sweepai/sweep')
      .blur()
    cy.get(messageInputSelector, { timeout: 10000 }).should(
      'have.attr',
      'placeholder',
      'Type a message...'
    )

    cy.get(messageInputSelector).type(testMessage + '{enter}')

    // Validate response from the LLM
    cy.get(':nth-child(2) > .transition-color', { timeout: 30000 }).should(
      'contain.text',
      'Analysis'
    )
    cy.url().then((url) => {
      expect(url.length).to.be.greaterThan(50)
    })
  })
})
