import re

UPDATES_MESSAGE = """\
### 🎉 Latest improvements to Sweep:

* Sweep now uses the `rope` library to refactor Python! Check out [Large Language Models are Bad at Refactoring Code](https://docs.sweep.dev/blogs/refactor-python). To have Sweep refactor your code, try `sweep: Refactor <your_file>.py`!
* Sweep finds and fixes bugs in your code by writing unit tests! Check out [Having GPT-4 Iterate on Unit Tests like a Human](https://docs.sweep.dev/blogs/ai-unit-tests).
"""

sep = "\n---\n"
bot_suffix_starring = ""
bot_suffix = (
    f"\n{sep}\n{UPDATES_MESSAGE}\n{sep} 💡 To recreate the pull request edit the issue"
    " title or description. To tweak the pull request, leave a comment on the pull request."
)
discord_suffix = f"\n<sup>[Join Our Discord](https://discord.com/invite/sweep)"

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
format_exit_code = lambda exit_code: "✓" if exit_code == 0 else f"❌ (`{exit_code}`)"


def create_collapsible(summary: str, body: str, opened: bool = False):
    return collapsible_template.format(
        summary=summary, body=body, opened="open" if opened else ""
    )


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
