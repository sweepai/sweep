from sweepai.core.context_pruning import ContextToPrune
from sweepai.utils.tree_utils import DirectoryTree

tree_str = """\
.assets/...
.github/...
.gitignore
.pre-commit-config.yaml
.replit
.vscode/...
CONTRIBUTING.md
Dockerfile
LICENSE
README.md
bin/...
docker-compose.yml
docs/
  .github/...
  .gitignore
  README.md
  Recipes.md
  components/...
  extension-post-install.md
  installation.md
  next-env.d.ts
  next.config.js
  package.json
  docs/pages/
    _meta.json
    about/...
    docs/pages/blogs/
      _meta.json
      ai-code-planning.mdx
      ai-unit-tests.mdx
      automate-tech-debt.mdx
      building-code-search.mdx
      chunking-2m-files.mdx
      chunking-improvements.mdx
      generating-50k-embeddings-with-gte.mdx
      giving-dev-tools.mdx
      gpt-32k-open-source.mdx
      gpt-4-modification.mdx
      index.mdx
      llm-sdk.mdx
      openai-proxy.mdx
      reading-docs.mdx
      refactor-python.mdx
      search-infra.mdx
      self-hosting.mdx
      super-linter.mdx
      sweeps-core-algo.mdx
      understanding-codebase-with-ctags.mdx
      zero-downtime-deployment.mdx
    deployment.mdx
    faq.mdx
    index.mdx
    privacy.mdx
    usage/...
    videos/...
  pnpm-lock.yaml
  public/...
  theme.config.tsx
  tsconfig.json
extension/...
minis3/...
notebooks/...
package.json
push_image.sh
pyproject.toml
redis.conf
sdk/...
self_deploy/...
sweep.yaml
sweepai/
  __init__.py
  sweepai/agents/
    assistant_modify.py
    assistant_wrapper.py
    complete_code.py
    complete_code_test.py
    graph_child.py
    graph_child_test.py
    graph_parent.py
    modify_bot.py
    move_bot.py
    name_agent.py
    name_agent_test.py
    pr_description_bot.py
    prune_modify_snippets.py
    refactor_bot.py
    refactor_bot_test.py
    sweep_yaml.py
    test_bot.py
    test_bot_test.py
    validate_code.py
  api.py
  config/...
  sweepai/core/
    __init__.py
    chat.py
    code_repair.py
    context_pruning.py
    documentation.py
    documentation_searcher.py
    entities.py
    external_searcher.py
    gha_extraction.py
    lexical_search.py
    post_merge.py
    prompts.py
    react.py
    repo_parsing_utils.py
    robots.py
    slow_mode_expand.py
    sweep_bot.py
    update_prompts.py
    vector_db.py
    webscrape.py
  events.py
  extension/...
  sweepai/handlers/
    __init__.py
    create_pr.py
    on_button_click.py
    on_check_suite.py
    on_comment.py
    on_merge.py
    on_review.py
    on_ticket.py
    on_ticket_test.py
    pr_utils.py
  health.py
  health_test.py
  logn/...
  pre_indexed_docs.py
  sandbox/...
  startup.py
  utils/...
tests/...
"""


response = """
"""

# context_to_prune = ContextToPrune.from_string(response)

tree = DirectoryTree()
tree.parse(tree_str)
serialized_list = ["README.md"]
# tree.remove_all_not_included(context_to_prune.paths_to_keep)
tree.remove_all_not_included(['sweepai/handlers/on_comment.py', 'sweepai/handlers/on_ticket.py', 'sweepai/core/sweep_bot.py'])
print()
print(tree)

# tree.expand_directory(context_to_prune.directories_to_expand)
tree.add_file_paths(serialized_list)
print()
print(tree)