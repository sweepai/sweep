from sweepai.core.chat import ChatGPT, call_llm
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

search_agent_instructions = """You are an expert software developer tasked with editing code to fulfill the user's request. Your goal is to make the necessary changes to the codebase while following best practices and respecting existing conventions. 

To complete the task, follow these steps:

1. If new functionality is required that doesn't fit into existing files, create a new file with an appropriate name and location.

2. Make the code changes in a targeted way:
    - Preserve existing whitespace, comments and code style
    - Make surgical edits to only the required lines of code
    - If a change is complex, break it into smaller incremental changes
    - Ensure each change is complete and functional before moving on
        When providing code snippets, be extremely precise with indentation:
        - Count the exact number of spaces used for indentation
        - If tabs are used, specify that explicitly 
        - Ensure the indentation of the code snippet matches the original file exactly
3. After making all the changes, review the modified code to verify it fully satisfies the original request.
4. Once you are confident the task is complete, submit the final solution.

In this environment, you have access to the following tools to assist in fulfilling the user request:

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

def search_codebase(
    question: str,
    cloned_repo: ClonedRepo,
):
    rcm = prep_snippets(
        cloned_repo,
        question,
        use_multi_query=False,
        NUM_SNIPPETS_TO_KEEP=0,
    )
    rcm.current_top_snippets = [snippet for snippet in rcm.current_top_snippets if snippet.score > 0.125][:5]

    for snippet in rcm.current_top_snippets:
        print(snippet.denotation, snippet.score)
    return rcm

def rag(
    question: str,
    cloned_repo: ClonedRepo,
):

    snippets_text = "\n\n".join([SNIPPET_FORMAT.format(
        denotation=snippet.denotation,
        contents=snippet.content,
    ) for snippet in rcm.current_top_snippets[::-1]])

    response = call_llm(
        system_prompt=rag_system_message,
        user_prompt=rag_user_message,
        params={
            "relevant_snippets": snippets_text,
            "question": question,
        },
    )

    return response