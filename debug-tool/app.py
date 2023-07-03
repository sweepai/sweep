import tkinter as tk
from tkinter import ttk

class Application(tk.Frame):
    def __init__(self, main_window):
        super().__init__(main_window)
        main_window.title("App with tabs and console")

        # Frame for the left side
        self.frame_left = tk.Frame(self)
        self.frame_left.pack(side="left", fill="y", expand=False)

        # Scrollbar for the listbox
        self.scrollbar = tk.Scrollbar(self.frame_left)
        self.scrollbar.pack(side="right", fill="y")

        # Listbox for tabs
        self.listbox = tk.Listbox(self.frame_left, yscrollcommand=self.scrollbar.set)
        for i in range(1, 11):
            self.listbox.insert(tk.END, f"Tab {i}")
        self.listbox.pack(side="left", fill="y")
        self.scrollbar.config(command=self.listbox.yview)

        # Frame for the right side
        self.frame_right = tk.Frame(self)
        self.frame_right.pack(side="right", fill="both", expand=True)

        # Text widget for console
        self.console = tk.Text(self.frame_right)
        self.console.pack(side="top", fill="both", expand=True)

        # Entry widget for user input
        self.entry = tk.Entry(self.frame_right)
        self.entry.pack(side="left", fill="x", expand=True)

        # Button for submitting user input
        self.button = tk.Button(self.frame_right, text="Submit", command=self.submit_input)
        self.button.pack(side="right")

        # Bind event for when a tab is selected
        self.listbox.bind("<<ListboxSelect>>", self.tab_selected)

        self.pack(fill="both", expand=True)

    def tab_selected(self, event):
        # Clear console
        self.console.delete('1.0', tk.END)

        # Write some example data into console when a tab is selected
        selected_tab = self.listbox.get(self.listbox.curselection())
        self.console.insert(tk.END, f"You have selected {selected_tab}.\nHere is some data...\n")
        for i in range(10):
            self.console.insert(tk.END, f"System: Tab {selected_tab} Data {i}\n")

    def submit_input(self):
        # Get user input and clear the entry box
        user_input = self.entry.get()
        self.entry.delete(0, tk.END)

        # Insert user input into console
        self.console.insert(tk.END, f"You: {user_input}\n")

main_window = tk.Tk()
app = Application(main_window)
app.mainloop()
