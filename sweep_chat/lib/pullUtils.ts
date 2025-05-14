import { PullRequest } from './types'

const isPullRequestEqual = (pr1: PullRequest, pr2: PullRequest) => {
  return (
    pr1.number === pr2.number &&
    pr1.branch === pr2.branch &&
    pr1.repo_name === pr2.repo_name &&
    pr1.title === pr2.title
  )
}

export { isPullRequestEqual }
