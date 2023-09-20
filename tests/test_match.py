from sweepai.utils.diff import find_best_match
from sweepai.utils.search_and_replace import score_multiline

haystack = """
<body>
    <nav class="navbar navbar-expand-lg bg-body-tertiary ">
        <div class="container-fluid">
          <a class="navbar-brand" href="#">THIS IS THE TITLE</a>

        </div>
      </nav>
    <div class="container pt-3">


        <div class="row">
          <div class="col-4">
            <div class="container">
"""

needle = """
<nav class="navbar navbar-expand-lg bg-body-tertiary ">
    <div class="container-fluid">
      <a class="navbar-brand" href="#">THIS IS THE TITLE</a>
    </div>
  </nav>
""".strip(
    "\n"
)

matched_section = """
    <nav class="navbar navbar-expand-lg bg-body-tertiary ">
        <div class="container-fluid">
          <a class="navbar-brand" href="#">THIS IS THE TITLE</a>

        </div>
      </nav>
""".strip(
    "\n"
)

# score = score_multiline(
#     needle.splitlines(),
#     matched_section.splitlines()
# )

best_match = find_best_match(needle, haystack)
print(best_match)
