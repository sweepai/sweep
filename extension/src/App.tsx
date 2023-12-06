import React, { useState, useRef } from "react";
import ShadowDomContainer from "./ShadowDomContainer";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";

const nonUglyTextboxCSS = {
  color: "white",
  background: "transparent",
  width: "100%",
  fontSize: 24,
  fontFamily:
    '-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji"',
  outline: "none",
  border: "none",
  "&:focus": {
    outline: "none",
  },
  "&::placeholder": {
    color: "white",
  },
};

const PoorMansModal = ({ children, onClose }) => {
  return (
    <Box
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "#222a",
        zIndex: 999,
      }}
      onClick={onClose}
    >
      <Box
        color="secondary"
        style={{
          backgroundColor: "#151215",
          borderColor: "0.5px solid #333",
          boxShadow: "0px 0px 20px 0 black",
          position: "absolute",
          top: "10%",
          left: "50%",
          transform: "translate(-50%, 0)",
          padding: 32,
          borderRadius: 10,
          minWidth: 1000,
          zIndex: 9999,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </Box>
    </Box>
  );
};

export default function App() {
  const [open, setOpen] = useState(false);
  const titleRef = useRef(null);
  const descriptionRef = useRef(null);
  const submitRef = useRef(null);

  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  document.onkeydown = function (e) {
    if (e.key === "Escape") {
      handleClose();
    } else if (e.key === "Enter" && e.ctrlKey) {
      if (!open) {
        handleOpen();
      } else if (submitRef.current) {
        submitRef.current.click();
      }
    }
  };

  const handleSubmit = () => {
    if (!titleRef.current.value) {
      alert("Please fill out both fields");
      return;
    }

    const title = titleRef.current.value;
    const description = descriptionRef.current.value || "";

    const issue = {
      title: title,
      body: description,
      repo: /github\.com\/(?<repo_full_name>[^\/]*\/[^\/]*)/.exec(window.location.href)!["groups"]!["repo_full_name"],
    };

    (async () => {
      try {
        const response = await chrome.runtime.sendMessage({
          type: "createIssue",
          issue,
        })

        if (!response["success"]) {
          alert("Something went wrong.")
        }
      } catch (error) {
        alert("Error creating issue " + error);
      }
    })();

    handleClose();
  };

  return (
    <ShadowDomContainer>
      <Button
        onClick={handleOpen}
        variant="outlined"
        style={{ marginBottom: 12, marginTop: 12 }}
        color="primary"
        fullWidth={true}
      >
        Make Sweep issue
      </Button>
      {open && (
        <PoorMansModal onClose={handleClose}>
          {/* */}
          <input
            placeholder='Write an api endpoint that does ... in the ... file ("Sweep:" prefix unneeded)'
            style={{
              ...nonUglyTextboxCSS,
              marginBottom: 12,
            }}
            onKeyDown={(e) => {
              if ((e.key === "Enter" && e.ctrlKey) || e.key === "Escape") {
                return;
              }
              e.stopPropagation();
            }}
            ref={titleRef}
            autoFocus
          />
          <textarea
            placeholder="The new endpoint should use the ... class from ... file because it contains ... logic."
            style={{
              ...nonUglyTextboxCSS,
              fontSize: 16,
              height: 300,
              resize: "none",
            }}
            ref={descriptionRef}
            onKeyDown={(e) => {
              if ((e.key === "Enter" && e.ctrlKey) || e.key === "Escape") {
                return;
              }
              e.stopPropagation();
            }}
          />
          <Box
            style={{
              width: "100%",
              display: "flex",
              justifyContent: "right",
            }}
          >
            <Button onClick={handleSubmit} ref={submitRef}>
              Submit
            </Button>
          </Box>
        </PoorMansModal>
      )}
    </ShadowDomContainer>
  );
}
