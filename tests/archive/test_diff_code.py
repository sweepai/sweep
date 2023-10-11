import difflib


def generate_diff(str1, str2):
    d = difflib.Differ()
    diff = d.compare(str1.splitlines(), str2.splitlines())
    return "\n".join(diff)


def git_conflict_format(diff_str):
    lines = diff_str.split("\n")
    output = []
    state = "neutral"

    UPDATED_MARKER = ">>>>>>> UPDATED"
    ORIGINAL_MARKER = "<<<<<<< ORIGINAL"
    SEPARATOR_MARKER = "======="

    for line in lines:
        if line.startswith("  "):
            if state == "add":
                output.append(UPDATED_MARKER)
            elif state == "del":
                output.extend([SEPARATOR_MARKER, UPDATED_MARKER])
            output.append(line[2:])
            state = "neutral"
        elif line.startswith("- "):
            if state == "neutral":
                output.append(ORIGINAL_MARKER)
            elif state == "add":
                output.extend([UPDATED_MARKER, ORIGINAL_MARKER])
            output.append(line[2:])
            state = "del"
        elif line.startswith("+ "):
            if state == "del":
                output.append(SEPARATOR_MARKER)
            elif state == "neutral":
                output.extend([ORIGINAL_MARKER, SEPARATOR_MARKER])
            output.append(line[2:])
            state = "add"

    if state == "add":
        output.append(UPDATED_MARKER)
    elif state == "del":
        output.extend([SEPARATOR_MARKER, UPDATED_MARKER])

    return "\n".join(output)


string1 = r"""
export default async function Home() {
  const eventsData = await fetchPostHogEventsData();
  const mongoEvents = await fetchEventsUsernameData();
  // const distinctIds = Array.from(new Set(eventsData.users.map((user: any) => user.distinct_id)));
  var distinctIds: string[] = [];
  for (const event of mongoEvents) {
    if (!distinctIds.includes(event.username) && !bannedUsers.includes(event.username)) {
      distinctIds.push(event.username);
    }
  }
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24" style={{background: 'linear-gradient(to bottom right, #0a0f18, #0a0022)'}}>
      {/* <SearchSelect style={{backgroundColor: "black"}}>
        {distinctIds.map((distinctId: string) => (
          <SearchSelectItem key={distinctId} value={distinctId} style={{backgroundColor: "darkgray"}}>
            {distinctId}
          </SearchSelectItem>
        ))}
      </SearchSelect> */}
      <div className="flex flex-wrap items-center justify-center">
        {distinctIds.map((distinctId: string, index: number) => (
          <a href={"/user/" + distinctId} className="text-white text-2xl hover:text-gray-400 mr-8" key={index}>
            {distinctId}
          </a>
        ))}
      </div>
    </main>
  )
}
"""
string2 = r"""
export default async function Home() {
  const eventsData = await fetchPostHogEventsData();
  const mongoEvents = await fetchEventsUsernameData();
  const distinctIds = Array.from(new Set(eventsData.users.map((user: any) => user.distinct_id)));
  for (const event of mongoEvents) {
    if (!distinctIds.includes(event.username) && !bannedUsers.includes(event.username)) {
      distinctIds.push(event.username);
    }
  }

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') {
        // trigger the "previous" button click event
      } else if (event.key === 'ArrowRight') {
        // trigger the "next" button click event
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24" style={{background: 'linear-gradient(to bottom right, #0a0f18, #0a0022)'}}>
      <SearchSelect style={{backgroundColor: "black"}}>
        {distinctIds.map((distinctId: string) => (
          <SearchSelectItem key={distinctId} value={distinctId} style={{backgroundColor: "darkgray"}}>
            {distinctId}
          </SearchSelectItem>
        ))}
      </SearchSelect>
      <div className="flex flex-wrap items-center justify-center">
        {distinctIds.map((distinctId: string, index: number) => (
          <a href={"/user/" + distinctId} className="text-white text-2xl hover:text-gray-400 mr-8" key={index}>
            {distinctId}
          </a>
        ))}
      </div>
    </main>
  )
}
"""

diff_result = generate_diff(string1, string2)
print(diff_result)
custom_diff_result = git_conflict_format(diff_result)
print(custom_diff_result)
