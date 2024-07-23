  useEffect(() => {
    if (initialRepoName) {
      setRepoName(initialRepoName)
      validateAndSetRepo(initialRepoName)
    }
  }, [initialRepoName])

  useEffect(() => {
    if (initialQuery && repoNameValid) {
      sendMessage()
    }
  }, [initialQuery, repoNameValid])

  const validateAndSetRepo = async (repoName: string) => {
    // Implementation of repo validation logic
    // This should be similar to the existing onBlur logic for the repo input
    // Set repoNameValid to true if validation succeeds
  }

  // ... rest of the component code ...