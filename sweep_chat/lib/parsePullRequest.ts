import { Octokit } from 'octokit'
import { PullRequest } from './types'
import { toast } from '@/components/ui/use-toast'

export default async function parsePullRequests(
  repoName: string,
  message: string,
  octokit: Octokit
): Promise<PullRequest[]> {
  const [orgName, repo] = repoName.split('/')
  const pulls = []

  try {
    const prURLs = message.match(
      new RegExp(
        `https?:\/\/github.com\/${repoName}\/pull\/(?<prNumber>[0-9]+)`,
        'gm'
      )
    )
    for (const prURL of prURLs || []) {
      const prNumber = prURL.split('/').pop()
      const pr = await octokit!.rest.pulls.get({
        owner: orgName,
        repo: repo,
        pull_number: parseInt(prNumber!),
      })
      const title = pr.data.title
      const body = pr.data.body
      const labels = pr.data.labels.map((label) => label.name)
      const status =
        pr.data.state === 'open' ? 'open' : pr.data.merged ? 'merged' : 'closed'
      const file_diffs = (
        await octokit!.rest.pulls.listFiles({
          owner: orgName,
          repo: repo,
          pull_number: parseInt(prNumber!),
        })
      ).data.sort((a, b) => {
        const aIsMarkdown =
          a.filename.endsWith('.md') || a.filename.endsWith('.rst')
        const bIsMarkdown =
          b.filename.endsWith('.md') || b.filename.endsWith('.rst')
        if (aIsMarkdown !== bIsMarkdown) {
          return aIsMarkdown ? 1 : -1
        }
        const statusOrder: Record<string, number> = {
          renamed: 0,
          copied: 1,
          added: 2,
          modified: 3,
          changed: 4,
          deleted: 5,
          unchanged: 6,
        }
        if (statusOrder[a.status] !== statusOrder[b.status]) {
          return statusOrder[a.status] - statusOrder[b.status]
        }
        return b.changes - a.changes
      })
      pulls.push({
        number: parseInt(prNumber!),
        repo_name: repoName,
        title,
        body,
        labels,
        status,
        file_diffs,
        branch: pr.data.head.ref,
      } as PullRequest)
    }

    return pulls
  } catch (e: any) {
    toast({
      title: 'Failed to retrieve pull request',
      description: `The following error has occurred: ${e.message}. Sometimes, logging out and logging back in can resolve this issue.`,
      variant: 'destructive',
    })
    return []
  }
}