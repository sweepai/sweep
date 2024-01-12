import pytest

from sweepai.core import context_pruning


def test_can_add_snippet():
    snippet = context_pruning.Snippet(file_path='test_path', start=0, end=10, content='test_content')
    current_snippets = [context_pruning.Snippet(file_path='test_path', start=0, end=10, content='test_content') for _ in range(10)]
    assert context_pruning.can_add_snippet(snippet, current_snippets) == True

def test_RepoContextManager():
    dir_obj = context_pruning.DirectoryTree()
    current_top_tree = 'test_tree'
    snippets = [context_pruning.Snippet(file_path='test_path', start=0, end=10, content='test_content') for _ in range(10)]
    snippet_scores = {'test_score': 0.5}
    cloned_repo = context_pruning.ClonedRepo('sweepai/sweep', 'test_id', 'main')
    repo_context_manager = context_pruning.RepoContextManager(dir_obj, current_top_tree, snippets, snippet_scores, cloned_repo)
    assert repo_context_manager.top_snippet_paths == ['test_path' for _ in range(10)]

def test_get_relevant_context():
    query = 'test_query'
    repo_context_manager = context_pruning.RepoContextManager(context_pruning.DirectoryTree(), 'test_tree', [context_pruning.Snippet(file_path='test_path', start=0, end=10, content='test_content') for _ in range(10)], {'test_score': 0.5}, context_pruning.ClonedRepo('sweepai/sweep', 'test_id', 'main'))
    ticket_progress = context_pruning.TicketProgress(tracking_id='test')
    assert context_pruning.get_relevant_context(query, repo_context_manager, ticket_progress, context_pruning.ChatLogger({'username': 'test'})) == repo_context_manager

def test_modify_context():
    thread = context_pruning.Thread()
    run = context_pruning.Run()
    repo_context_manager = context_pruning.RepoContextManager(context_pruning.DirectoryTree(), 'test_tree', [context_pruning.Snippet(file_path='test_path', start=0, end=10, content='test_content') for _ in range(10)], {'test_score': 0.5}, context_pruning.ClonedRepo('sweepai/sweep', 'test_id', 'main'))
    ticket_progress = context_pruning.TicketProgress(tracking_id='test')
    assert context_pruning.modify_context(thread, run, repo_context_manager, ticket_progress) == None
