from sweepai.utils.diff import generate_new_file_from_patch

old_file = r"""
import ExternalLinkWithText from "./ExternalLinkWithText";
const demo = require("../assets/demo.mp4");

export default class CallToAction extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      spin: false,
    };
  }
  // const canvas = document.getElementById('canvas3d');
  // const app = new Application(canvas);
  // app.load('https://prod.spline.design/jzV1MbbHCyCmMG7u/scene.splinecode');
  return (
    <Container maxW={"5xl"}>
      <Stack
"""

old_file = r"""
def filter_file(file, sweep_config):
    for ext in sweep_config.exclude_exts:
        if file.endswith(ext):
            return False
    for dir_name in sweep_config.exclude_dirs:
        if file[len("repo/") :].startswith(dir_name):
            return False
    if not os.path.isfile(file):
        return False
    with open(file, "rb") as f:
        is_binary = False
        for block in iter(lambda: f.read(1024), b""):
            if b"\0" in block:
                is_binary = True
                break
        if is_binary:
            return False

    with open(file, "rb") as f:
        if len(f.read()) > 60000:
            return False
    return True
"""

# code_replaces = """
# ```
# <<<< ORIGINAL
# export default class CallToAction extends React.Component {
#   constructor(props) {
#     super(props);
#     this.state = {
#       spin: false,
#     };
#   }
#   return (
#     <Container maxW={"5xl"}>
# ====
# export default class CallToAction extends React.Component {
#   constructor(props) {
#     super(props);
#     this.state = {
#       spin: false,
#     };
#   }
#   render() {
#     return (
#       <Container maxW={"5xl"}>
# >>>> UPDATED
# ```
# """

code_replaces = """
<<<< ORIGINAL
with open(file, "rb") as f:
    if len(f.read()) > 60000:
        return False
====
if os.stat(file).st_size > 60000:
    return False
>>>> UPDATED
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
    # generate_new_file_from_patch(code_replaces, old_file)[0]
