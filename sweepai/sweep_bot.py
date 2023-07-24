import modal
import openai
import github

def create_gha_pr(sweep_bot):
    branch_name = sweep_bot.create_branch("gha-setup")
    sweep_bot.repo.create_file(
        'sweep.yaml',
        'Enable GitHub Actions',
        'gha_enabled: True',
        branch=branch_name
    )
    pr_title = "Enable GitHub Actions"
    pr_description = "This PR enables GitHub Actions for this repository."
    pr = sweep_bot.repo.create_pull(
        title=pr_title,
        body=pr_description,
        head=branch_name,
        base=SweepConfig.get_branch(sweep_bot.repo),
    )
    pr.add_to_labels(GITHUB_LABEL_NAME)
