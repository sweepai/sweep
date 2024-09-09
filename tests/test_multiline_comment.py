from sweepai.dataclasses.comments import CommentDiffSpan
from sweepai.utils.github_utils import get_github_client, get_installation_id
from sweepai.utils.diff import get_diff_spans


old_content = '''
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%PUBLIC_URL%/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta 
      name="description"
      content="Sweep is an AI coding assistant."
    />
    <link rel="apple-touch-icon" href="%PUBLIC_URL%/logo192.png" />
    <meta
      property="og:title" 
      content="Sweep: turn bugs and feature requests into code changes."
    />
    <meta
      property="og:description"
      content="Sweep is an assistant that handles your Github tickets."
    />

    <!--
      manifest.json provides metadata used when your web app is installed on a
      user's mobile device or desktop. See https://developers.google.com/web/fundamentals/web-app-manifest/
    -->
    <link rel="manifest" href="%PUBLIC_URL%/manifest.json" />
    <!--
      Notice the use of %PUBLIC_URL% in the tags above.
      It will be replaced with the URL of the `public` folder during the build.
      Only files inside the `public` folder can be referenced from the HTML.

      Unlike "/favicon.ico" or "favicon.ico", "%PUBLIC_URL%/favicon.ico" will
      work correctly both with client-side routing and a non-root public URL.
      Learn how to configure a non-root public URL by running `npm run build`.
    -->
    <title>Sweep: turn bugs and feature requests into code changes.</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
    <!--
      This HTML file is a template.
      If you open it directly in the browser, you will see an empty page.

      You can add webfonts, meta tags, or analytics to this file.
      The build step will place the bundled scripts into the <body> tag.

      To begin the development, run `npm start` or `yarn start`.
      To create a production bundle, use `npm run build` or `yarn build`.
    -->
  </body>
</html>

'''

new_content = '''
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%PUBLIC_URL%/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#ffffff" />
    <meta 
      name="description"
      content="Sweep is an AI coding assistant."
    />
    <link rel="apple-touch-icon" href="%PUBLIC_URL%/logo192.png" />
    <meta
      property="og:title" 
      content="Sweep: turn bugs and feature requests into code changes."
    />
    <meta
      property="og:title"
      content="Sweep is an ai assistant that handles your Github tickets."
    />

    <!--
      manifest.json provides metadata used when your web app is installed on a
      user's mobile device or desktop. See https://developers.google.com/web/fundamentals/web-app-manifest/
    -->
    <link rel="manifest" href="%PUBLIC_URL%/manifest.json" />
    <!--
      Unlike "/favicon.ico" or "favicon.ico", "%PUBLIC_URL%/favicon.ico" will
      work correctly both with client-side routing and a non-root public URL.
      Learn how to configure a non-root public URL by running `npm run build`.
    -->
    <title>Sweep: turn bugs and feature requests into code changes.</title>
  </head>
  <body>
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
    <!--
      This HTML file is a template.
      If you open it directly in the browser, you will see an empty page.

      You can add webfonts, meta tags, or analytics to this file.
      The build step will place the bundled scripts into the <body> tag.

      To begin the development, run `npm start` or `yarn start`.
      To create a production bundle, use `npm run build` or `yarn build`.
    -->
  </body>
</html>

'''

file_name = "public/index.html"

org_name = "sweepai"
repo_name = "e2e"
pr_number = 1314
installation_id = get_installation_id(org_name)
print("Fetching access token...")
_token, g = get_github_client(installation_id)
repo = g.get_repo(f"{org_name}/{repo_name}")
pr = repo.get_pull(pr_number)
diff_spans = get_diff_spans(old_content, new_content, file_name)

def start_review(pr):
    import requests
    api_url = f"https://api.github.com/repos/{repo.full_name}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "commit_id": pr.get_commits().reversed[0].sha,
        "body": "Starting a review for suggestion comments",
        "event": "COMMENT"
    }
    response = requests.post(api_url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["id"]
    else:
        print(f"Failed to start a review. Status code: {response.status_code}")
        print(f"Error message: {response.text}")
        return None

def create_review_comment(pr, diff_span: CommentDiffSpan, review_id: int) -> bool:
    import requests
    api_url = f"https://api.github.com/repos/{repo.full_name}/pulls/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "body": f"```suggestion\n{diff_span.new_code}\n```",
        "path": diff_span.file_name,
        "line": diff_span.old_end_line,
        "start_line": diff_span.old_start_line,
        "side": "RIGHT",
        "pull_request_review_id": review_id
    }
    response = requests.post(api_url, headers=headers, json=data)
    if response.status_code == 201:
        print("Review comment created successfully!")
    else:
        print(f"Failed to create review comment. Status code: {response.status_code}")
        print(f"Error message: {response.text}")
    return response.status_code == 201

def submit_review(pr, review_id: int):
    import requests
    api_url = f"https://api.github.com/repos/{repo.full_name}/pulls/{pr_number}/reviews/{review_id}/events"
    headers = {
        "Authorization": f"Bearer {_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "event": "COMMENT"
    }
    response = requests.post(api_url, headers=headers, json=data)
    if response.status_code == 200:
        print("Review submitted successfully!")
    else:
        print(f"Failed to submit review. Status code: {response.status_code}")
        print(f"Error message: {response.text}")

review_id = start_review(pr)
if review_id:
    for diff_span in diff_spans:
        create_review_comment(pr, diff_span, review_id)
    submit_review(pr, review_id)