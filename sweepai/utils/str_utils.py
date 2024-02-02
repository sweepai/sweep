import hashlib
import os
import re
import time

UPDATES_MESSAGE = """\
<details>
<summary><b>🎉 Latest improvements to Sweep:</b></summary>
<ul>
<li>New <a href="https://progress.sweep.dev">dashboard</a> launched for real-time tracking of Sweep issues, covering all stages from search to coding.</li>
<li>Integration of OpenAI's latest Assistant API for more efficient and reliable code planning and editing, improving speed by 3x.</li>
<li>Use the <a href="https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-pull-request-github">GitHub issues extension</a> for creating Sweep issues directly from your editor.</li>
</ul>
</details>
"""

BOT_SUFFIX = (
    ("\n\n*This is an automated message generated by [Sweep AI](https://sweep.dev).*")
    if not os.environ.get("GITHUB_PAT")
    else ""
)

sep = "\n---\n"
bot_suffix_starring = ""
bot_suffix = (
    f"\n{sep}\n{UPDATES_MESSAGE}\n\n💡 To recreate the pull request edit the issue"
    " title or description."
)
discord_suffix = "<sup>Something wrong? [Let us know](https://discord.gg/sweep).</sup>"

stars_suffix = ""

collapsible_template = """
<details {opened}>
<summary>{summary}</summary>

{body}
</details>
"""

checkbox_template = "- [{check}] {filename}\n{instructions}\n"

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2

ordinal = lambda n: str(n) + (
    "th" if 4 <= n <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
)
format_sandbox_success = lambda success: "✓" if success else f"❌ (`Sandbox Failed`)"


def create_collapsible(summary: str, body: str, opened: bool = False):
    return collapsible_template.format(
        summary=summary, body=body, opened="open" if opened else ""
    )


def inline_code(text: str):
    return f"<code>{text}</code>" if text else ""


def code_block(text: str):
    return f"<pre>{text}</pre>" if text else ""


def blockquote(text: str):
    text = text.replace("\n•", "<br/>•")
    return f"<blockquote>{text}\n</blockquote>" if text else ""


def create_checkbox(title: str, body: str, checked: bool = False):
    return checkbox_template.format(
        check="X" if checked else " ", filename=title, instructions=body
    )


def strip_sweep(text: str):
    return (
        re.sub(
            r"^[Ss]weep\s?(\([Ss]low\))?(\([Mm]ap\))?(\([Ff]ast\))?\s?:", "", text
        ).lstrip(),
        re.search(r"^[Ss]weep\s?\([Ss]low\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Mm]ap\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ss]ubissues?\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ss]andbox?\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ff]ast\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ll]int\)", text) is not None,
    )


def clean_logs(logs: str):
    cleaned_logs = re.sub(r"\x1b\[.*?[@-~]", "", logs.replace("```", "\`\`\`"))
    cleaned_logs = re.sub("\n{2,}", "\n", cleaned_logs)
    cleaned_logs = re.sub("\r{2,}", "\n", cleaned_logs)
    cleaned_logs = cleaned_logs.strip("\n")
    cleaned_logs = cleaned_logs or "(nothing was outputted)"
    return cleaned_logs


def extract_lines(text: str, start: int, end: int):
    lines = text.splitlines(keepends=True)
    return "\n".join(lines[max(0, start) : min(len(lines), end)])


def add_line_numbers(text: str, start: int = 0):
    lines = text.splitlines(keepends=True)
    return "".join(f"{start + i} | {line}" for i, line in enumerate(lines))


def to_branch_name(s, max_length=40):
    branch_name = s.strip().lower().replace(" ", "_")
    branch_name = re.sub(r"[^a-z0-9_]", "", branch_name)
    return branch_name[:max_length]


def get_hash():
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]
