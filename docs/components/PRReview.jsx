

export default ({ repoName, prId }) => {
    const [prData, setPrData] = useState(null);
  
    useEffect(() => {
      const fetchPRData = async () => {
        try {
          const response = await fetch(`https://api.github.com/repos/${repoName}/pulls/${prId}`);
          const data = await response.json();
          setPrData(data);
        } catch (error) {
          console.error("Error fetching PR data:", error);
        }
      };
  
      fetchPRData();
    }, [repoName, prId]);
  
    if (!prData) {
      return <div>Loading...</div>;
    }
  
    return (
      <div>
        <h2>{prData.title}</h2>
        <p>By: {prData.user.login}</p>
        <p>{prData.body}</p>
        <a href={prData.html_url} target="_blank" rel="noopener noreferrer">View on GitHub</a>
      </div>
    );
  };