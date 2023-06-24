# Example usage:
from src.utils.diff import generate_new_file, join_contents_k


old_file_content = """<old_file>
0:'''
1:On Github ticket, get ChatGPT to deal with it
2:'''
3:
4:# TODO:Add file validation
5:
6:import os
7:import openai
8:
9:from loguru import logger
10:
11:from src.core.sweep_bot import SweepBot
12:from src.handlers.on_review import get_pr_diffs
13:from src.utils.event_logger import posthog
14:from src.utils.github_utils import (
15:    get_github_client,
16:    search_snippets,
17:)
18:from src.utils.prompt_constructor import HumanMessageCommentPrompt
19:from src.utils.constants import PREFIX
20:
21:github_access_token = os.environ.get("GITHUB_TOKEN")
22:openai.api_key = os.environ.get("OPENAI_API_KEY")
23:
24:
25:def on_comment(
26:    repo_full_name:str,
27:    repo_description:str,
28:    comment:str,
29:    pr_path:str | None,
30:    pr_line_position:int | None,
31:    username:str,
32:    installation_id:int,
33:    pr_number:int = None,
34:):
35:    # Flow:
36:    # 1. Get relevant files
37:    # 2:Get human message
38:    # 3. Get files to change
39:    # 4. Get file changes
40:    # 5. Create PR
41:    logger.info(f"Calling on_comment() with the following arguments:{comment}, {repo_full_name}, {repo_description}, {pr_path}")
42:    organization, repo_name = repo_full_name.split("/")
43:    metadata = {
44:        "repo_full_name":repo_full_name,
45:        "repo_name":repo_name,
46:        "organization":organization,
47:        "repo_description":repo_description,
48:        "installation_id":installation_id,
49:        "username":username,
50:        "function":"on_comment",
51:        "mode":PREFIX,
52:    }
53:
54:    posthog.capture(username, "started", properties=metadata)
55:    logger.info(f"Getting repo {repo_full_name}")
56:    try:
57:        g = get_github_client(installation_id)
58:        repo = g.get_repo(repo_full_name)
59:        pr = repo.get_pull(pr_number)
60:        branch_name = pr.head.ref
61:        pr_title = pr.title
62:        pr_body = pr.body
63:        diffs = get_pr_diffs(repo, pr)
64:        snippets, tree = search_snippets(repo, comment, installation_id, branch=branch_name, num_files=1 if pr_path else 3)
65:        pr_line = None
66:        pr_file_path = None
67:        if pr_path and pr_line_position:
68:            pr_file = repo.get_contents(pr_path, ref=branch_name).decoded_content.decode("utf-8")
69:            pr_lines = pr_file.splitlines()
70:            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
71:            pr_file_path = pr_path.strip()
72:
73:        logger.info("Getting response from ChatGPT...")
74:        human_message = HumanMessageCommentPrompt(
75:            comment=comment,
76:            repo_name=repo_name,
77:            repo_description=repo_description if repo_description else "",
78:            diffs=diffs,
79:            issue_url=pr.html_url,
80:            username=username,
81:            title=pr_title,
82:            tree=tree,
83:            summary=pr_body,
84:            snippets=snippets,
85:            pr_file_path=pr_file_path, # may be None
86:            pr_line=pr_line, # may be None
87:        )
88:        logger.info(f"Human prompt{human_message.construct_prompt()}")
89:        sweep_bot = SweepBot.from_system_message_content(
90:            # human_message=human_message, model="claude-v1.3-100k", repo=repo
91:            human_message=human_message, repo=repo, 
92:        )
93:    except Exception as e:
94:        posthog.capture(username, "failed", properties={
95:            "error":str(e),
96:            "reason":"Failed to get files",
97:            **metadata
98:        })
99:        raise e
100:
101:    try:
102:        logger.info("Fetching files to modify/create...")
103:        file_change_requests = sweep_bot.get_files_to_change()
104:
105:        logger.info("Making Code Changes...")
106:        sweep_bot.change_files_in_github(file_change_requests, branch_name)
107:
108:        logger.info("Done!")
109:    except Exception as e:
110:        posthog.capture(username, "failed", properties={
111:            "error":str(e),
112:            "reason":"Failed to make changes",
113:            **metadata
114:        })
115:        raise e
116:
117:    posthog.capture(username, "success", properties={**metadata})
118:    logger.info("on_comment success")
119:    return {"success":True}
120:
</old_file>"""

modify_file_response = """
<new_file>
<copied>0-73</copied>
def is_comment_addressed(comment: str) -> bool:
    addressed_keywords = ["addressed", "resolved", "fixed"]
    return any(keyword in comment.lower() for keyword in addressed_keywords)

from src.core.react import react_to_comment

<copied>74-88</copied>
if is_comment_addressed(comment):
    react_to_comment(comment_id, 'eyes')

<copied>89-120</copied>
# Last section
</new_file>
"""
new_file = generate_new_file(modify_file_response, old_file_content)
# print(new_file)

old_file_content = """0:'''
1:On Github ticket, get ChatGPT to deal with it
2:'''
3:
4:# TODO: Add file validation
5:
6:import os
7:import openai
8:
9:from loguru import logger
10:import modal
11:
12:from src.core.entities import Snippet
13:from src.core.prompts import (
14:    reply_prompt,
15:)
16:from src.core.sweep_bot import SweepBot
17:from src.core.prompts import issue_comment_prompt
18:from src.handlers.on_review import review_pr
19:from src.utils.event_logger import posthog
20:from src.utils.github_utils import get_github_client, search_snippets
21:from src.utils.prompt_constructor import HumanMessagePrompt
22:from src.utils.constants import DB_NAME, PREFIX
23:
24:github_access_token = os.environ.get("GITHUB_TOKEN")
25:openai.api_key = os.environ.get("OPENAI_API_KEY")
26:
27:update_index = modal.Function.lookup(DB_NAME, "update_index")
28:
29:bot_suffix = "I'm a bot that handles simple bugs and feature requests \
30:but I might make mistakes. Please be kind!"
31:
32:collapsible_template = '''
33:<details>
34:  <summary>{summary}</summary>
35:
36:  {body}
37:</details>
38:'''
39:
40:chunker = modal.Function.lookup("utils", "Chunking.chunk")
41:
42:num_of_snippets_to_query = 10
43:max_num_of_snippets = 5
44:
45:def on_ticket(
46:    title: str,
47:    summary: str,
48:    issue_number: int,
49:    issue_url: str,
50:    username: str,
51:    repo_full_name: str,
52:    repo_description: str,
53:    installation_id: int,
54:    comment_id: int = None
55:):
56:    # Check if the title starts with "sweep" or "sweep: " and remove it
57:    if title.lower().startswith("sweep: "):
58:        title = title[7:]
59:    elif title.lower().startswith("sweep "):
60:        title = title[6:]
61:
62:    # Flow:
63:    # 1. Get relevant files
64:    # 2: Get human message
65:    # 3. Get files to change
66:    # 4. Get file changes
67:    # 5. Create PR
68:
69:    organization, repo_name = repo_full_name.split("/")
70:    metadata = {
71:        "issue_url": issue_url,
72:        "issue_number": issue_number,
73:        "repo_full_name": repo_full_name,
74:        "organization": organization,
75:        "repo_name": repo_name,
76:        "repo_description": repo_description,
77:        "username": username,
78:        "installation_id": installation_id,
79:        "function": "on_ticket",
80:        "mode": PREFIX,
81:    }
82:    posthog.capture(username, "started", properties=metadata)
83:
84:    g = get_github_client(installation_id)
85:
86:    if comment_id:
87:        logger.info(f"Replying to comment {comment_id}...")
88:    logger.info(f"Getting repo {repo_full_name}")
89:    repo = g.get_repo(repo_full_name)
90:    current_issue = repo.get_issue(number=issue_number)
91:    if current_issue.state == 'closed':
92:        posthog.capture(username, "issue_closed", properties=metadata)
93:        return {"success": False, "reason": "Issue is closed"}
94:    item_to_react_to = current_issue.get_comment(comment_id) if comment_id else current_issue
95:    eyes_reaction = item_to_react_to.create_reaction("eyes")
96:
    def comment_reply(message: str):
98:        current_issue.create_comment(message + "\n\n---\n" + bot_suffix)
99:
100:    comments = current_issue.get_comments()
101:    replies_text = ""
102:    if comment_id:
103:        replies_text = "\nComments:\n" + "\n".join(
104:            [
105:                issue_comment_prompt.format(
106:                    username=comment.user.login,
                    reply=comment.body,
                ) for comment in comments
            ]
        )
111:
112:    def fetch_file_contents_with_retry():
113:        retries = 3
114:        error = None
115:        for i in range(retries):
116:            try:
117:                logger.info(f"Fetching relevant files for the {i}th time...")
118:                return search_snippets(
119:                    repo,
120:                    f"{title}\n{summary}\n{replies_text}",
121:                    num_files=num_of_snippets_to_query,
122:                    branch=None,
123:                    installation_id=installation_id,
124:                )
125:            except Exception as e:
126:                error = e
127:                continue
128:        posthog.capture(
129:            username, "fetching_failed", properties={"error": error, **metadata}
130:        )
131:        raise error
132:
133:    # update_index.call(
134:    #     repo_full_name,
135:    #     installation_id=installation_id,
136:    # )
137:
138:    logger.info("Fetching relevant files...")
139:    try:
140:        snippets, tree = fetch_file_contents_with_retry()
141:        assert len(snippets) > 0
142:    except Exception as e:
143:        logger.error(e)
144:        comment_reply(
145:            "It looks like an issue has occured around fetching the files. Perhaps the repo has not been initialized: try removing this repo and adding it back. I'll try again in a minute. If this error persists contact team@sweep.dev."
146:        )
147:        raise e
148:
149:    # reversing to put most relevant at the bottom
150:    snippets: list[Snippet] = snippets[::-1]
151:
152:    num_full_files = 2
153:    num_extended_snippets = 2
154:
155:    most_relevant_snippets = snippets[-num_full_files:]
156:    snippets = snippets[:-num_full_files]
157:    logger.info("Expanding snippets...")
158:    for snippet in most_relevant_snippets:
159:        current_snippet = snippet
160:        _chunks, metadatas, _ids = chunker.call(
161:            current_snippet.content, 
162:            current_snippet.file_path
163:        )
164:        segmented_snippets = [
165:            Snippet(
166:                content=current_snippet.content,
167:                start=metadata["start"],
168:                end=metadata["end"],
169:                file_path=metadata["file_path"],
170:            ) for metadata in metadatas
171:        ]
172:        index = 0
173:        while index < len(segmented_snippets) and segmented_snippets[index].start <= current_snippet.start:
174:            index += 1
175:        index -= 1
176:        for i in range(index + 1, min(index + num_extended_snippets + 1, len(segmented_snippets))):
177:            current_snippet += segmented_snippets[i]
178:        for i in range(index - 1, max(index - num_extended_snippets - 1, 0), -1):
179:            current_snippet = segmented_snippets[i] + current_snippet
180:        snippets.append(current_snippet)
181:
182:    # snippet fusing
183:    i = 0
184:    while i < len(snippets):
185:        j = i + 1
186:        while j < len(snippets):
187:            if snippets[i] ^ snippets[j]:  # this checks for overlap
188:                snippets[i] = snippets[i] | snippets[j]  # merging
189:                snippets.pop(j)
190:            else:
191:                j += 1
192:        i += 1
193:
194:    snippets = snippets[:min(len(snippets), max_num_of_snippets)]
195:
196:    human_message = HumanMessagePrompt(
197:        repo_name=repo_name,
198:        issue_url=issue_url,
199:        username=username,
200:        repo_description=repo_description,
201:        title=title,
202:        summary=summary + replies_text,
203:        snippets=snippets,
204:        tree=tree, # TODO: Anything in repo tree that has something going through is expanded
205:    )
206:    sweep_bot = SweepBot.from_system_message_content(
207:        human_message=human_message, repo=repo, is_reply=bool(comments)
208:    )
209:    sweepbot_retries = 3
210:    try:
211:        for i in range(sweepbot_retries):
212:            logger.info("CoT retrieval...")
213:            if sweep_bot.model == "gpt-4-32k-0613":
214:                sweep_bot.cot_retrieval()
215:            logger.info("Fetching files to modify/create...")
216:            file_change_requests = sweep_bot.get_files_to_change()
217:            logger.info("Getting response from ChatGPT...")
218:            reply = sweep_bot.chat(reply_prompt, message_key="reply")
219:            sweep_bot.delete_messages_from_chat("reply")
220:            logger.info("Sending response...")
221:            new_line = '\n'
222:            comment_reply(
223:                reply
224:                + "\n\n"
225:                + collapsible_template.format(
226:                    summary="Some code snippets I looked at (click to expand). If some file is missing from here, you can mention the path in the ticket description.",
227:                    body="\n".join(
228:                        [
229:                            f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{min(snippet.end, snippet.content.count(new_line))}\n"
230:                            for snippet in snippets[::-1]
231:                        ]
232:                    ),
233:                )
234:            )
235:
236:            logger.info("Generating PR...")
237:            pull_request = sweep_bot.generate_pull_request()
238:
239:            logger.info("Making PR...")
240:            pull_request.branch_name = sweep_bot.create_branch(pull_request.branch_name)
241:            sweep_bot.change_files_in_github(file_change_requests, pull_request.branch_name)
242:
243:            pr_description = f"{pull_request.content} Fixes #{issue_number}. To checkout this PR branch, run the following command in your terminal
244:
245:            pr = repo.create_pull(
246:                title=pull_request.title,
247:                body=pr_description,
248:                head=pull_request.branch_name,
249:                base=repo.default_branch,
250:            )
251:            current_issue.create_reaction("rocket")
252:            try:
253:                review_pr(repo=repo, pr=pr, issue_url=issue_url, username=username, 
254:                        repo_description=repo_description, title=title, 
255:                        summary=summary, replies_text=replies_text, installation_id=installation_id, snippets=snippets, tree=tree)
256:            except Exception as e:
257:                logger.error(e)
258:            break
259:    except openai.error.InvalidRequestError as e:
260:        logger.error(e)
261:        comment_reply(
262:            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. If this error persists contact team@sweep.dev."
263:        )
264:        posthog.capture(
265:            username,
266:            "failed",
267:            properties={
268:                "error": str(e),
269:                "reason": "Invalid request error / context length",
270:                **metadata,
271:            },
272:        )
273:        raise e
274:    except Exception as e:
275:        logger.error(e)
276:        comment_reply(
277:            "I'm sorry, but it looks like an error has occured. Try removing and re-adding the sweep label. If this error persists contact team@sweep.dev."
278:        )
279:        posthog.capture(
280:            username,
281:            "failed",
282:            properties={"error": str(e), "reason": "Generic error", **metadata},
283:        )
284:        raise e
285:    else:
286:        try:
287:            eyes_reaction.delete()
288:        except:
289:            pass
290:        item_to_react_to.create_reaction("rocket")
291:
292:    posthog.capture(username, "success", properties={**metadata})
293:    logger.info("on_ticket success")
294:    return {"success": True}
295:
"""

modify_file_response = """
<new_file>
<copied>0-97</copied>
    def comment_reply(message: str):
        comment = current_issue.create_comment(message + "\n\n---\n" + bot_suffix)
        comment.create_reaction("eyes")
<copied>99-94</copied>
    comments = current_issue.get_comments()
    replies_text = ""
    if comment_id:
        replies_text = "\nComments:\n" + "\n".join(
            [
                issue_comment_prompt.format(
                    username=comment.user.login,
                    reply=comment.body,
                ) for comment in comments
            ]
        )
<copied>112-294</copied>
</new_file>
"""
new_file = generate_new_file(modify_file_response, old_file_content)
# print(new_file)

def test_join_contents_k():
    a = """\
a
b
"""
    b = """\
b
b
"""
    expected_result = """\
a
b
b"""

    assert join_contents_k(a, b, 2) == expected_result
    a = """\
a
b
"""
    b = """\
a
b
"""
    expected_result = """\
a
b
"""
    assert join_contents_k(a, b, 2) == expected_result
    a = """\
x
y
a
b
c
"""
    b = """\
a
b
c
d
"""
    expected_result = """\
x
y
a
b
c
d"""
    assert join_contents_k(a, b, 2) != expected_result
    assert join_contents_k(a, b, 4) == expected_result

test_join_contents_k()

old_file_content = '''\
"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import os
import openai

from loguru import logger

from src.core.sweep_bot import SweepBot
from src.handlers.on_review import get_pr_diffs
from src.utils.event_logger import posthog
from src.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from src.utils.prompt_constructor import HumanMessageCommentPrompt
from src.utils.constants import PREFIX

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")


def on_comment(
    repo_full_name: str,
    repo_description: str,
    comment: str,
    pr_path: str | None,
    pr_line_position: int | None,
    username: str,
    installation_id: int,
    pr_number: int = None,
):
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    logger.info(f"Calling on_comment() with the following arguments: {comment}, {repo_full_name}, {repo_description}, {pr_path}")
    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "organization": organization,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "username": username,
        "function": "on_comment",
        "mode": PREFIX,
    }

    posthog.capture(username, "started", properties=metadata)
    logger.info(f"Getting repo {repo_full_name}")
    try:
        g = get_github_client(installation_id)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        branch_name = pr.head.ref
        pr_title = pr.title
        pr_body = pr.body
        diffs = get_pr_diffs(repo, pr)
        snippets, tree = search_snippets(repo, comment, installation_id, branch=branch_name, num_files=1 if pr_path else 3)
        pr_line = None
        pr_file_path = None
        if pr_path and pr_line_position:
            pr_file = repo.get_contents(pr_path, ref=branch_name).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
            pr_file_path = pr_path.strip()

        logger.info("Getting response from ChatGPT...")
        human_message = HumanMessageCommentPrompt(
            comment=comment,
            repo_name=repo_name,
            repo_description=repo_description if repo_description else "",
            diffs=diffs,
            issue_url=pr.html_url,
            username=username,
            title=pr_title,
            tree=tree,
            summary=pr_body,
            snippets=snippets,
            pr_file_path=pr_file_path, # may be None
            pr_line=pr_line, # may be None
        )
        logger.info(f"Human prompt{human_message.construct_prompt()}")
        sweep_bot = SweepBot.from_system_message_content(
            # human_message=human_message, model="claude-v1.3-100k", repo=repo
            human_message=human_message, repo=repo, 
        )
    except Exception as e:
        posthog.capture(username, "failed", properties={
            "error": str(e),
            "reason": "Failed to get files",
            **metadata
        })
        raise e

    try:
        logger.info("Fetching files to modify/create...")
        file_change_requests = sweep_bot.get_files_to_change()

        logger.info("Making Code Changes...")
        sweep_bot.change_files_in_github(file_change_requests, branch_name)

        logger.info("Done!")
    except Exception as e:
        posthog.capture(username, "failed", properties={
            "error": str(e),
            "reason": "Failed to make changes",
            **metadata
        })
        raise e

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_comment success")
    return {"success": True}
'''
    
modify_file_response = '''<new_file>
<copied>0-21</copied>
def add_reaction_to_comment(g, comment_id):
    """
    Add an "eyes" reaction to a comment using the Github API.

    Args:
        g: The Github client.
        comment_id: The id of the comment to react to.
    """
    g.get_repo().get_issue_comment(comment_id).create_reaction('eyes')
<copied>22-106</copied>
add_reaction_to_comment(g, comment.id)
<copied>107-120</copied>
</new_file>'''

print("\n".join([f"{idx}:{line}" for idx, line in enumerate(generate_new_file(modify_file_response, old_file_content).splitlines())]))