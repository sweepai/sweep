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

code_replaces = """
<<<< ORIGINAL
export default class CallToAction extends React.Component {
put whatever you want here gpt4
    <Container maxW={"5xl"}>
====
export default class CallToAction extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      spin: false,
    };
  }
  render() {
    return (
      <Container maxW={"5xl"}>
>>>> UPDATED
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
    # generate_new_file_from_patch(code_replaces, old_file)[0]
