import github

from sweepai.core.entities import FileChangeRequest, Message
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.chat_logger import ChatLogger

old_file = """\
import React from "react";
import { EmailIcon, HamburgerIcon } from "@chakra-ui/icons";
import {
  Box,
  Button,
  ButtonGroup,
  Flex,
  HStack,
  IconButton,
  Image,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  useBreakpointValue,
} from "@chakra-ui/react";
import { Link } from "react-router-dom";
import { FaDiscord, FaGithub, FaTwitter } from "react-icons/fa";
import logo from "../assets/icon.png";


export default function NavBar() {
  const listDisplay = useBreakpointValue({ base: "none", lg: "flex" });
  const menuDisplay = useBreakpointValue({ base: "flex", lg: "none" });
  const navItems = [
    {
      label: "Twitter",
      icon: <FaTwitter />,
      link: "https://twitter.com/sweep__ai",
    },
    {
      label: "Github",
      icon: <FaGithub />,
      link: "https://github.com/sweepai/sweep",
    },
    {
      label: "Discord",
      icon: <FaDiscord />,
      link: "https://discord.gg/sweep",
    },
    {
      label: "Email",
      icon: <EmailIcon />,
      link: "mailto:team@sweep.dev",
    },
    // {
    //   label: "Buy Sweep Pro",
    //   icon: <p>Buy Sweep Pro</p>,
    //   link: "https://buy.stripe.com/fZe03512h99u0AE6os",
    // },
  ];


  return (
    <Box as="nav" bg="bg-surface" boxShadow="sm" width="full" p={4}>
      <HStack spacing="10" justify="space-between">
        <Flex justify="space-between" flex="1">
          <HStack>
            <Link to="/">
              <Button variant="ghost">
                <Image src={logo} alt="logo" width={10} borderRadius={12} />
                Sweep AI
              </Button>
            </Link>
            <Button
              variant="ghost"
              onClick={() => window.open("https://docs.sweep.dev", "_blank")}
            >
              Documentation
            </Button>
            <Link to="/about-us">
              <Button variant="ghost">About Us</Button>
            </Link>
            {/* Removed conditional rendering of PricingModal */}
          </HStack>
          <ButtonGroup variant="link" display={listDisplay}>
            {navItems.map((item) => (
              <IconButton
                key={item.label}
                icon={item.icon}
                variant="ghost"
                aria-label={item.label}
                onClick={() => {
                  window.open(item.link, "_blank");
                }}
                px={2}
              />
            ))}
            {/* Added PricingModal to always be displayed */}
            <Link to="/pricing">
              <Button variant="ghost">Pricing</Button>
            </Link>
          </ButtonGroup>
          <Menu>
            <MenuButton
              as={IconButton}
              aria-label="Options"
              icon={<HamburgerIcon />}
              variant="outline"
              display={menuDisplay}
            />
            <MenuList backgroundColor="#333">
              {navItems.map((item) => (
                <MenuItem backgroundColor="#333">
                  {item.label}
                  {item.label !== "Buy Sweep Pro" && (
                    <IconButton
                      key={item.label}
                      icon={item.icon}
                      variant="ghost"
                      aria-label={item.label}
                      onClick={() => {
                        window.open(item.link, "_blank");
                      }}
                    />
                  )}
                </MenuItem>
              ))}
            </MenuList>
          </Menu>
        </Flex>
      </HStack>
    </Box>
  );
}\
"""

section = """\
export default function NavBar() {
  const listDisplay = useBreakpointValue({ base: "none", lg: "flex" });
  const menuDisplay = useBreakpointValue({ base: "flex", lg: "none" });
  const navItems = [
    {
      label: "Twitter",
      icon: <FaTwitter />,
      link: "https://twitter.com/sweep__ai",
    },
    {
      label: "Github",
      icon: <FaGithub />,
      link: "https://github.com/sweepai/sweep",
    },
    {
      label: "Discord",
      icon: <FaDiscord />,
      link: "https://discord.gg/sweep",
    },
    {
      label: "Email",
      icon: <EmailIcon />,
      link: "mailto:team@sweep.dev",
    },
    // {
    //   label: "Buy Sweep Pro",
    //   icon: <p>Buy Sweep Pro</p>,
    //   link: "https://buy.stripe.com/fZe03512h99u0AE6os",
    // },
  ];\
"""

sweep_bot = SweepBot.from_system_message_string(
  "", 
  repo=github.Github().get_repo("sweepai/sweep"),
  chat_logger=ChatLogger(data={"username": "kevinlu1248"})
)

sweep_bot.messages.extend([
  Message(
    role="assistant",
    content="""
Contextual thoughts: 
* The Navbar component in src/components/Navbar.tsx is currently a functional component. I need to understand its current structure and functionality in order to refactor it into a class component.
* The useBreakpointValue hook is being used in the Navbar component. I need to understand how it's being used in order to replace it with this.state and this.setState in the class component.
* The current unit tests in src/App.test.tsx provide a starting point for writing the new unit tests for the refactored component. I need to understand what functionality they're testing.


Relevant snippets:




<snippet source="src/App.test.tsx:1-11">
 import { screen } from "@testing-library/react"
 import { render } from "./test-utils"
 import { App } from "./App"
 
 test("renders learn react link", () => {
   render(<App />)
   const linkElement = screen.getByText(/learn chakra/i)
   expect(linkElement).toBeInTheDocument()
 })
</snippet>"""
  ),
  Message(
    role="user",
    content="""# Repo & Issue Metadata
Repo: landing-page: No description provided.
Issue Url: https://github.com/sweepai/landing-page/issues/420
Username: sweep-nightly[bot]
Issue Title: Refactor Navbar to class component
Issue Description: * In src/components/Navbar.tsx, define a class Navbar that extends React.Component.
* In src/components/Navbar.tsx, implement a render method that returns the same JSX as the functional component.
* In src/components/Navbar.tsx, replace the use of useBreakpointValue with this.state and this.setState.
* In src/components/Navbar.tsx, write unit tests for the refactored component and run them to verify that they pass.


Parent issue: #335


Additional instructions:
* In src/components/Navbar.tsx, define a class Navbar that extends React.Component. The class should have a constructor that initializes the state and binds any necessary methods.
* In the render method of the Navbar class, return the same JSX as the functional component. Make sure to replace any hooks with their class component equivalents.
* Replace the use of useBreakpointValue with this.state and this.setState. This may involve adding a resize event listener in componentDidMount and componentWillUnmount to update the state when the window size changes.
* Write unit tests for the Navbar class in a new file, src/components/Navbar.test.tsx. The tests should cover the same functionality as the existing tests for the functional component, as well as any new functionality introduced by the refactoring.
* Run the tests using the command `npm test` to verify that they pass."""
  )
])

# print(
#   sweep_bot.rewrite_section(
#     FileChangeRequest(
#         filename="main.py",
#         instructions="Rewrite as class component",
#         change_type="rewrite",
#     ),
#     old_file,
#     section,
#   ).section
# )

print(
  sweep_bot.rewrite_file(
    FileChangeRequest(
        filename="index.js",
        instructions="Rewrite as class component",
        change_type="rewrite",
    ),
    old_file,
  )
)
