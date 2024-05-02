from copy import deepcopy
from sweepai.agents.modify import validate_and_parse_function_call
from sweepai.core.chat import ChatGPT, call_llm
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.ticket_utils import prep_snippets

instructions = r"""Respond in the following XML format:

<analysis>
For each snippet, summarize the contents and what it deals with. Indicate all sections of code that are relevant to the user's question. Think step-by-step to reason about how the snippets relate to the question.
</analysis>

<answer>
Provide a detailed response to the user's question. Reference all relevant entities in the codebase, and provide examples of usages and implementations whenever possible. Be precise when you reference entities by indicating the file they are from like this: `foo.bar(x, y)` (from `src/modules/foo:Foo`).
</answer>

<sources>
<file_name>path/to/file.py</file_name>
<file_name>path/to/other/file.py:a-b</file_name>
</sources>"""

example = """Here's an illustrative example of how to structure your response:

<example>
<example_input>
<snippet>
<file_name>models/user.js</file_name>
<source>
const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
  name: String,
  email: String,
  password: String,
  posts: [{ type: mongoose.Schema.Types.ObjectId, ref: 'Post' }]
});

userSchema.methods.addPost = function(postId) {
  if (!this.posts.includes(postId)) {
    this.posts.push(postId);
    return this.save();
  }
  return Promise.resolve(this);
};

module.exports = mongoose.model('User', userSchema);
</source>
</snippet>

<snippet>
<file_name>models/post.js</file_name>
<source>
const mongoose = require('mongoose');

const postSchema = new mongoose.Schema({
  title: String,
  content: String,
  author: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  likes: [{ type: mongoose.Schema.Types.ObjectId, ref: 'User' }]
});

postSchema.methods.addLike = function(userId) {
  if (!this.likes.includes(userId)) {
    this.likes.push(userId);
    return this.save();
  }
  return Promise.resolve(this);
};

module.exports = mongoose.model('Post', postSchema);
</source>
</snippet>

<snippet>
<file_name>pages/api/posts/[id]/like.js</file_name>
<source>
import dbConnect from 'lib/dbConnect';
import Post from 'models/post';

export default async function handler(req, res) {
  await dbConnect();

  const { id } = req.query;
  const { userId } = req.body;

  const post = await Post.findById(id);
  if (!post) {
    return res.status(404).json({ message: 'Post not found' });
  }

  await post.addLike(userId);
  res.status(200).json(post);
}
</source>
</snippet>

<snippet>
<file_name>pages/api/users/[id]/posts.js</file_name>
<source>
import dbConnect from 'lib/dbConnect';
import User from 'models/user';

export default async function handler(req, res) {
  await dbConnect();

  const { id } = req.query;
  const { postId } = req.body;

  const user = await User.findById(id);
  if (!user) {
    return res.status(404).json({ message: 'User not found' });  
  }

  await user.addPost(postId);
  res.status(200).json(user);
}
</source>
</snippet>

<snippet>
<file_name>lib/dbConnect.js</file_name>
<source>
import mongoose from 'mongoose';

const MONGODB_URI = process.env.MONGODB_URI;

if (!MONGODB_URI) {
  throw new Error('Please define the MONGODB_URI environment variable');
}

let cached = global.mongoose;

if (!cached) {
  cached = global.mongoose = { conn: null, promise: null };
}

async function dbConnect() {
  if (cached.conn) {
    return cached.conn;
  }

  if (!cached.promise) {
    cached.promise = mongoose.connect(MONGODB_URI).then(mongoose => mongoose);
  }
  cached.conn = await cached.promise;
  return cached.conn;
}

export default dbConnect;
</source>
</snippet>

<question>
When a POST request is made to /api/posts/[id]/like with a userId in the request body, explain in detail what happens in the system to process the like. How are the User and Post models involved and what fields and methods are used? How does the data flow through the different files and what is the final result in the database?
</question>
</example_input>

<example_output>
<analysis>
The POST request to `/api/posts/[id]/like` is handled in `pages/api/posts/[id]/like.js`. This file imports and uses the `Post` model (defined in `models/post.js`) to find the post by `_id` and add the like using the `userId` from the request body. The `likes` field (an array of `User` refs) and `addLike` method (defined in `models/post.js`) of the `Post` model are utilized.

While not directly used in processing the like, the `User` model (`models/user.js`) contains a `posts` field referencing the user's posts, establishing the relationship between `User` and `Post` models.

Database connection is managed by `lib/dbConnect.js`, which imports `mongoose`, checks for the `MONGODB_URI` environment variable, and exports a `dbConnect` function. This function is called in the API route (`pages/api/posts/[id]/like.js`) to ensure a connection.

Upon successfully adding the like, the updated `post` document is returned in the API response, with the `likes` array now containing the new `userId`.
</analysis>

<answer>
When a POST request is made to `/api/posts/[id]/like` with a `userId` in the request body, the system processes the like as follows:

1. The request is routed to `pages/api/posts/[id]/like.js` based on the file structure. The `id` parameter is extracted from the query.

Example usage of the API route:
```javascript
const response = await fetch('/api/posts/post123/like', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ userId: 'user456' })
});
```

2. In the route handler (`pages/api/posts/[id]/like.js`), `lib/dbConnect.js` is imported and `dbConnect()` is called to ensure a MongoDB connection. 

3. The `Post` model is imported from `models/post.js`. It defines the schema for posts, including the `likes` field (array of `User` refs) and the `addLike` method.

4. `Post.findById(id)` (`pages/api/posts/[id]/like.js`) is called to find the post document by `_id`. If not found, a 404 error is returned.

Example implementation of `Post.findById`:
```javascript
const post = await Post.findById(id);
if (!post) {
  return res.status(404).json({ message: 'Post not found' });
}
```

5. If found, `post.addLike(userId)` (`pages/api/posts/[id]/like.js`) is called, invoking the `addLike` method (defined in `models/post.js`) on the `post` instance.

6. `addLike` (`models/post.js`) checks if `userId` exists in `likes` using `includes()`. If not, `userId` is pushed to `likes` and the `post` is saved, updating the database. If `userId` is already present, the `post` is not modified.

Example implementation of `addLike`:
```javascript
postSchema.methods.addLike = function(userId) {
  if (!this.likes.includes(userId)) {
    this.likes.push(userId);
    return this.save();
  }
  return Promise.resolve(this);
};
```

7. The updated `post` document is returned in the JSON response with a 200 status (`pages/api/posts/[id]/like.js`). 

In summary, `/api/posts/[id]/like` uses the `Post` model (`models/post.js`) to find the post, add the `userId` to its `likes` array, and update the database. The `User` model (`models/user.js`) defines the user-post relationship but is not directly involved.

The result is the post document in the database having the new `userId` added to its `likes` array.
</answer>

<sources>
models/user.js
models/post.js
pages/api/posts/[id]/like.js
lib/dbConnect.js
</sources>
</example_output>
</example>

Notice how when the example mentions an entity, it references the class and file it is from. This helps in providing a clear and precise response."""

rag_system_message = """You are a helpful assistant who can answer questions about a codebase. You will be provided relevant code snippets. Please analyze the snippets, indicate which ones are relevant to answering the question, and provide a detailed answer.

""" + instructions + "\n\n" + example

rag_user_message = """Here are relevant snippets from the codebase in increasing order of relevance:

<relevant_snippets>
{relevant_snippets}
</relevant_snippets>

Here is the user's question:

<question>
{question}
</question>

""" + instructions

SNIPPET_FORMAT = """<snippet>
<file_name>{denotation}</file_name>
<source>
{contents}
</source>
</snippet>"""

tools_available = """You have access to the following tools to assist in fulfilling the user request:
<tool_description>
<tool_name>search_codebase</tool_name>
<description>
</description>
<parameters>
<parameter>
<name>question</name>
<type>str</type>
<description>
Detailed, specific natural language search question to search the codebase for relevant snippets. This should be in the form of a natural language question, like "What is the structure of the User model in the authentication module?"
</description>
</parameter>
<parameter>
<name>include_docs</name>
<type>str</type>
<description>
(Optional) Include documentation in the search results. Default is false.
</description>
</parameter>
<parameter>
<name>include_tests</name>
<type>str</type>
<description>
(Optional) Include test files in the search results. Default is false.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_task</tool_name>
<description>
Once you have collected and analyzed the relevant snippets, use this tool to submit the final response to the user's question.
</description>
<parameters>
<parameter>
<name>analysis</name>
<type>str</type>
<description>
Firstly, analyze all search results so far to determine the final answer. Then, for each retrieved snippet so far, summarize the contents, what it deals with, and how it can help answer the user's question. Indicate all sections of code that are relevant to the user's question. Think step-by-step to reason about how the snippets relate to the question.
</description>
</parameter>
<parameter>
<name>answer</name>
<type>str</type>
<description>
Provide a precise, detailed response to the user's question.

Make reference to entities in the codebase, and provide examples of usages and implementations whenever possible. 

When you mention an entity, be precise and clear by indicating the file they are from. For example, you may say: this functionality is accomplished by calling `foo.bar(x, y)` (from the `Foo` class in `src/modules/foo.py`). If you do not know where it is from, you need use the search_codebase tool to find it.
</description>
</parameter>
<parameter>
<name>sources</name>
<type>str</type>
<description>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Follow this format:
path/to/file.ext
path/to/other/file.ext
</description>
</parameter>
</parameters>
</tool_description>"""

example_tool_calls = """Here are examples of how to use the tools:

To search the codebase for relevant snippets:
<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>Where are the push notification configurations and registration logic implemented using the Firebase Cloud Messaging library in the mobile app codebase?</question>
</parameters>
</invoke>
</function_call>

Notice that the `query` parameter is an extremely detailed, specific natural language search question.

<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>Where is the documentation that details how to configure the authentication module for the Stripe payments webhook? Is anything related to this detailed in docs/reference/stripe-configuration.mdx?</question>
<include_docs>true</include_docs>
</parameters>
</invoke>
</function_call>

Notice that `include_docs` is set to true since we are retrieving documentation in this case. Also notice how the question is very specific, directed, with references to specific files or modules.

The above are just illustrative examples. Make sure to provide detailed, specific questions to search for relevant snippets in the codebase and only make one function call."""

search_agent_instructions = """You are an expert software developer tasked with finding relevant information in the codebase to resolve the user's request.

To complete the task, follow these steps:

1. Analyze the user's question to understand the information they are seeking.
2. Search the codebase for relevant code snippets that can help answer the question.
3. Provide a detailed response to the user's question based on the code snippets found.

In this environment, you have access to the following tools to assist in fulfilling the user request:

Use one tool at a time. Before every time you use a tool, think step-by-step in a <scratchpad> block about which tools you need to use and in what order to find the information needed to answer the user's question.

Once you have collected and analyzed the relevant snippets, use the `submit_task` tool to submit the final response to the user's question.

You MUST call them like this:
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>

Here are the tools available:
"""

search_agent_user_message = """Here is the user's question:

<request>
{question}
</request>

Now find the relevant code snippets in the codebase to answer the question. Use the `search_codebase` tool to search for snippets. Provide the query to search for relevant snippets in the codebase."""

NO_TOOL_CALL_PROMPT = """FAILURE
Your last function call was incorrectly formatted. Here is are examples of correct function calls:

For example, to search the codebase for relevant snippets:

<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>How is the User model defined in the authentication module for the Stripe payements webhook?</question>
</parameters>
</invoke>
</function_call>

If you have sufficient sources to answer the question, call the submit_task function with an extremely detailed, well-referenced response in the following format:

<function_call>
<invoke>
<tool_name>submit_task</tool_name>
<parameters>
<analysis>
For each snippet, summarize the contents and what it deals with. Indicate all sections of code that are relevant to the user's question. Think step-by-step to reason about how the snippets relate to the question.
</analysis>
<answer>
Provide a detailed response to the user's question.

Reference all relevant entities in the codebase, and provide examples of usages and implementations whenever possible. 

When you mention an entity, be precise and clear by indicating the file they are from. For example, you may say: this functionality is accomplished by calling `foo.bar(x, y)` (from the `Foo` class in `src/modules/foo.py`).
</answer>
<sources>
Code files you referenced in your <answer>. Only include sources that are DIRECTLY REFERENCED in your answer, do not provide anything vaguely related. Keep this section MINIMAL. These must be full paths and not symlinks of aliases to files. Follow this format:
path/to/file.ext
path/to/other/file.ext
</sources>
</parameters>
</invoke>
</function_call>

First, in a scratchpad, think step-by-step to analyze the search results and determine whether the source results retrieved so far are sufficient. Also determine why your last function call weas incorrectly formatted. Then, you may make additional search queries using search_codebase or submit the task using submit_task."""

DEFAULT_FUNCTION_CALL = """<function_call>
<invoke>
<tool_name>search_codebase</tool_name>
<parameters>
<question>{question}</question>
</parameters>
</invoke>
</function_call>"""

def search_codebase(
    question: str,
    cloned_repo: ClonedRepo,
    *args,
    **kwargs,
):
    rcm = prep_snippets(
        cloned_repo,
        question,
        use_multi_query=False,
        NUM_SNIPPETS_TO_KEEP=0,
        *args,
        **kwargs
    )
    rcm.current_top_snippets = [snippet for snippet in rcm.current_top_snippets][:5]
    return rcm

def rag(
    question: str,
    cloned_repo: ClonedRepo,
):

    # snippets_text = "\n\n".join([SNIPPET_FORMAT.format(
    #     denotation=snippet.denotation,
    #     contents=snippet.content,
    # ) for snippet in rcm.current_top_snippets[::-1]])

    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=search_agent_instructions + tools_available + "\n\n" + example_tool_calls,
    )

    user_message = search_agent_user_message.format(question=question)
    llm_state = {
        "visited_snippets": set()
    }

    for iter_num in range(10):
        if iter_num == 0:
            response = DEFAULT_FUNCTION_CALL.format(question=question)
        else:
            response = chat_gpt.chat_anthropic(
                user_message,
                stop_sequences=["</function_call>"],
            ) + "</function_call>"

        function_call = validate_and_parse_function_call(
            response,
            chat_gpt
        )

        if function_call is None:
            user_message = NO_TOOL_CALL_PROMPT
        else:
            function_call_response = handle_function_call(function_call, cloned_repo, llm_state)
            user_message = f"<function_output>\n{function_call_response}\n</function_output>"
        
        if "DONE" == function_call_response:
            return function_call.function_parameters.get("answer"), function_call.function_parameters.get("sources")

    return response

def handle_function_call(function_call: AnthropicFunctionCall, cloned_repo: ClonedRepo, llm_state: dict):
    if function_call.function_name == "search_codebase":
        if "question" not in function_call.function_parameters:
            return "Please provide a question to search the codebase."
        question = function_call.function_parameters["question"]
        rcm = search_codebase(
            question=question,
            cloned_repo=cloned_repo,
            include_docs=function_call.function_parameters.get("include_docs", "false") == "true",
            include_tests=function_call.function_parameters.get("include_tests", "false") == "true",
        )
        snippets = []
        prev_visited_snippets = deepcopy(llm_state["visited_snippets"])
        for snippet in rcm.current_top_snippets[::-1]:
            if snippet.denotation not in llm_state["visited_snippets"]:
                snippets.append(SNIPPET_FORMAT.format(
                    denotation=snippet.denotation,
                    contents=snippet.content,
                ))
                llm_state["visited_snippets"].add(snippet.denotation)
            else:
                snippets.append(f"Snippet already retrieved previously: {snippet.denotation}")
        snippets_string = "\n\n".join(snippets)
        snippets_string += f"\n\nYour last search query was \"{question}\". Here is a list of all the files retrieved in this search query:\n" + "\n".join([f"- {snippet.denotation}" for snippet in rcm.current_top_snippets])
        if prev_visited_snippets:
            snippets_string += "\n\nHere is a list of all the files retrieved previously:\n" + "\n".join([f"- {snippet}" for snippet in sorted(list(prev_visited_snippets))])
        snippets_string += f"\n\nThe above are the snippets that are found in decreasing order of relevance to the search query \"{function_call.function_parameters.get('question')}\"."
        for snippet in rcm.current_top_snippets:
            print(snippet.denotation, snippet.score)
        return snippets_string + "\n\nFirst, think step-by-step in a scratchpad to analyze the search results and determine whether the answers provided here are sufficient or if there are additional relevant modules that we may need, such as referenced utility files, docs or tests.\n\nThen, if the search results are insufficient, you must make additional more highly specified different but related search queries using search_codebase. Otherwise, if you have found all the relevant information, submit the task using submit_task. If you submit, be sure that the <sources> section is MINIMAL and only includes all files you reference in your answer. Be sure to use the valid function call format."
    if function_call.function_name == "submit_task":
        for key in ("analysis", "answer", "sources"):
            if key not in function_call.function_parameters:
                return f"Please provide a {key} to submit the task."
        return "DONE"
    else:
        return "ERROR\n\nInvalid tool name."

if __name__ == "__main__":
    cloned_repo = MockClonedRepo(
        _repo_dir = "/tmp/sweep",
        repo_full_name="sweepai/sweep",
    )
    rag(
        question="What version of django are we using?",
        cloned_repo=cloned_repo,
    )