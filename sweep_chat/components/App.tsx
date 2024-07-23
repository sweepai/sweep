  const sendMessage = async (messageToSend: string = currentMessage) => {
    posthog_capture('chat submitted')
    let newMessages: Message[] = [
      ...messages,
      { content: messageToSend, role: 'user' },
    ]
    setMessages(newMessages)
    setCurrentMessage('')
    const pulls = await parsePullRequests(repoName, messageToSend, octokit!)
    if (pulls.length) {
      setUserMentionedPullRequest(pulls[pulls.length - 1])
      setCommitToPR(true)
    }