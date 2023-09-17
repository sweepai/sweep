#!/usr/bin/env python3

import curses
import os
import json

def get_latest_files(path, count=10):
    # Get all files in the directory along with their last modified times
    files = [(f, os.path.getmtime(os.path.join(path, f))) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and f.endswith(".json")]

    # Sort files by modification time
    sorted_files = sorted(files, key=lambda x: x[1], reverse=True)

    # Return the 'count' latest files
    return [f[0] for f in sorted_files[:count]]

def load_files(path, latest_files):
    # Create the "tables" list based on the files
      tables = []
      for f in latest_files:
          with open(os.path.join(path, f), 'r') as file:
              data = json.load(file)
              if "state" in data:
                  tables.append(data)
      return tables

def main(stdscr):
    # Initialize curses
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_YELLOW, -1)  # Yellow text for Running
    curses.init_pair(2, curses.COLOR_GREEN, -1)   # Green text for Done
    curses.init_pair(3, curses.COLOR_RED, -1)     # Red text for Errored
    curses.init_pair(4, curses.COLOR_WHITE, -1)  # Grey text for Exited


    # Path to the directory
    path = "logn_logs/meta/"

    # Get the 10 latest edited files
    latest_files = get_latest_files(path)

    # tables = load_files(latest_files)

    # Animation sequence for "Running"
    running_anim = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    anim_index = 0

    # Make getch non-blocking
    stdscr.nodelay(True)

    while True:
        # Clear screen
        stdscr.clear()

        tables = load_files(path, latest_files)


        # Display the status of each table
        for idx, table in enumerate(tables, start=1):
            if table["state"] == "Running" or table["state"] == "Created" or not table["state"]:
                stdscr.addstr(idx, 10, f"Table {idx}: {running_anim[anim_index]} (Running)", curses.color_pair(1))
            elif table["state"] == "Done":
                stdscr.addstr(idx, 10, f"Table {idx}: ✅ (Done)", curses.color_pair(2))
            elif table["state"] == "Errored":
                stdscr.addstr(idx, 10, f"Table {idx}: ❌ (Errored)", curses.color_pair(3))
            elif table["state"] == "Exited":
                stdscr.addstr(idx, 10, f"Table {idx}: ⬛ (Exited)", curses.color_pair(4))

        # Update the animation index
        anim_index = (anim_index + 1) % len(running_anim)

        # Refresh the screen
        stdscr.refresh()

        # Check for input
        ch = stdscr.getch()
        if ch == ord('q'):
            break

        curses.napms(100)  # delay for 100ms

try:
  curses.wrapper(main)
except:
  print("Closed.")
