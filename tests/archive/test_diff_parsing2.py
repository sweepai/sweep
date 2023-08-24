from sweepai.utils.diff import generate_new_file_from_patch

old_file = r"""
import {
  Flex,
  Container,
  Heading,
  Stack,
  Text,
  Button,
} from "@chakra-ui/react";
import { tsParticles } from "tsparticles";
import { loadConfettiPreset } from "tsparticles-preset-confetti";
import { FaDiscord, FaGithub } from "react-icons/fa";
import { useState } from "react";
import logo from "../assets/icon.png";

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
        textAlign={"center"}
        align={"center"}
        spacing={{ base: 8, md: 10 }}
        py={{ base: 4, md: 15 }}
        style={{ paddingTop: "0 !important" }}
        mb={36}
      >
        <img src={logo} alt="Logo" style={{ width: '200px', animation: this.state.spin ? "spin 0.5s linear" : "bob 0.75s ease-in-out infinite alternate", marginTop: "-2rem !important", borderRadius: "50%" }} onClick={this.handleClick} />
        {/* <img src={logo} alt="Logo" width={120} height={120} style={{
          animation: "bob 0.75s ease-in-out infinite alternate",
        }} /> */}
        <style>
          {`
            @keyframes bob {
              from {
                transform: translateY(0);
              }
              to {
                transform: translateY(15px);
              }
            }
            @keyframes spin {
              from {
                transform: rotate(0deg) scale(1);
              }
              to {
                transform: rotate(360deg);
              }
            }
          `}
        </style>
        <Heading
          fontWeight={600}
          fontSize={{ base: "3xl", sm: "4xl", md: "6xl" }}
          lineHeight={"110%"}
          mt="0 !important"
        >
          Ship code faster
        </Heading>
        <Text color={"purple.400"} maxW={"3xl"} mt="1rem !important" mb="1rem !important">
          Let Sweep handle your tech debt so you can focus on the exciting problems
        </Text>
        <Button
          color="white"
          p={6}
          colorScheme={"purple"}
          bg={"purple.400"}
          _hover={{ bg: "purple.600" }}
          onClick={() => window.open("https://github.com/apps/sweep-ai")}
          fontSize={"xl"}
          mb="1rem !important"
        >
          <FaGithub />&nbsp;&nbsp;Install Sweep
        </Button>
        <ExternalLinkWithText
          href="https://discord.gg/sweep" // updated link
          color="purple.400"
          mt="0 !important"
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
          }}
        >
          <FaDiscord />&nbsp;&nbsp;Join our Discord
        </ExternalLinkWithText>
        <Flex w={"full"} mt="4rem !important">
          <Container width="100vw" boxShadow="0 0 80px #181818" p={0} maxWidth="full">
            <video src={demo} autoPlay muted loop playsInline>
              Your browser does not support the video tag.
            </video>
          </Container>
        </Flex>
      </Stack>
    </Container>
  );
};
"""

code_replaces = """
```
<<<< ORIGINAL
export default class CallToAction extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      spin: false,
    };
  }
  return (
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
```
"""

if __name__ == "__main__":
    print(generate_new_file_from_patch(code_replaces, old_file)[0])
    # generate_new_file_from_patch(code_replaces, old_file)[0]
