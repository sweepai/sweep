/// <reference types="cypress" />
// ***********************************************
// This example commands.ts shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --
// Cypress.Commands.add('login', (email, password) => { ... })
//
//
// -- This is a child command --
// Cypress.Commands.add('drag', { prevSubject: 'element'}, (subject, options) => { ... })
//
//
// -- This is a dual command --
// Cypress.Commands.add('dismiss', { prevSubject: 'optional'}, (subject, options) => { ... })
//
//
// -- This will overwrite an existing command --
// Cypress.Commands.overwrite('visit', (originalFn, url, options) => { ... })
//
// declare global {
//   namespace Cypress {
//     interface Chainable {
//       login(email: string, password: string): Chainable<void>
//       drag(subject: string, options?: Partial<TypeOptions>): Chainable<Element>
//       dismiss(subject: string, options?: Partial<TypeOptions>): Chainable<Element>
//       visit(originalFn: CommandOriginalFn, url: string, options: Partial<VisitOptions>): Chainable<Element>
//     }
//   }
// }

declare module 'cypress' {
  namespace Cypress {
    interface Chainable {
      /**
       * Custom command to perform login.
       */
      login(): Chainable
    }
  }
}

const loginSecureCookie = Cypress.env('LOGIN_SECURE_COOKIE')
const loginSessionCookie = Cypress.env('LOGIN_SESSION_COOKIE')

if (!loginSessionCookie && !loginSecureCookie) {
  throw new Error(
    'Login cookies are not set, you must set one of the following environment variables: LOGIN_SESSION_COOKIE or LOGIN_SECURE_COOKIE'
  )
}

// @ts-ignore
Cypress.Commands.add('login', () => {
  cy.session('mySession', () => {
    // We need to refresh this cookie once in a while.
    // We are unsure if this is true and if true, when it needs to be refreshed.
    // console.log(loginSessionCookie)
    if (loginSessionCookie) {
      cy.setCookie('next-auth.session-token', loginSessionCookie)
    }
    if (loginSecureCookie) {
      cy.setCookie('__Secure-next-auth.session-token', loginSecureCookie, {
        secure: true,
      })
    }
  })
})
