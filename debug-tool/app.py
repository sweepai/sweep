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

        # Create Label for the chat person's name at the top
        self.label_chat_name = tk.Label(self.frame_right, text="System", font=("Arial", 16))
        self.label_chat_name.pack(side="top", fill="x")

        # Create a Canvas for messages
        self.canvas = tk.Canvas(self.frame_right)
        self.canvas.pack(side="top", fill="both", expand=True)

        # Add a Scrollbar to the Canvas
        self.scrollbar_chat = tk.Scrollbar(self.frame_right, command=self.canvas.yview)
        self.scrollbar_chat.pack(side='right', fill='y')

        # Configure the Canvas
        self.canvas.configure(yscrollcommand=self.scrollbar_chat.set)
        self.canvas.bind('<Configure>', lambda e: self.canvas.configure(scrollregion = self.canvas.bbox("all")))

        # Create an interior Frame for messages
        self.frame_messages = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.frame_messages, anchor='nw')

        # Frame for user input
        self.frame_input = tk.Frame(self.frame_right)
        self.frame_input.pack(side="bottom", fill="x")

        # Entry widget for user input
        self.entry = tk.Entry(self.frame_input)
        self.entry.pack(side="left", fill="x", expand=True)

        # Button for submitting user input
        self.button = tk.Button(self.frame_input, text="Submit", command=self.submit_input)
        self.button.pack(side="right")

        # Bind event for when a tab is selected
        self.listbox.bind("<<ListboxSelect>>", self.tab_selected)

        self.pack(fill="both", expand=True)

        self.message_count = 0

    def tab_selected(self, event):
        # Clear console
        self.clear_messages()

        # Write some example data into console when a tab is selected
        selected_tab = self.listbox.get(self.listbox.curselection())
        self.label_chat_name.config(text=f"Chatting with {selected_tab}")
        for i in range(10):
            self.add_message(f"Tab {selected_tab} Data {i}", "right")

    def clear_messages(self):
        for message in self.frame_messages.winfo_children():
            message.destroy()
        self.message_count = 0

    def add_message(self, message, side):
        text = tk.Text(self.frame_messages, height=3, wrap="word", bd=2, relief="solid", padx=2, pady=2)
        text.insert(1.0, message)
        text.tag_configure("right", justify="right")
        text.tag_add("right", 1.0, "end")
        text.configure(state="disabled")

        if side == "right":
            self.frame_messages.grid_columnconfigure(0, weight=1)
            self.frame_messages.grid_columnconfigure(1, weight=1000)
            text.grid(row=self.message_count, column=1, sticky='ne')
        else:
            self.frame_messages.grid_columnconfigure(0, weight=1000)
            self.frame_messages.grid_columnconfigure(1, weight=1)
            text.grid(row=self.message_count, column=0, sticky='nw')

        self.message_count += 1

    def submit_input(self):
        # Get user input and clear the entry box
        user_input = self.entry.get()
        self.entry.delete(0, tk.END)

        # Insert user input into console
        self.add_message(user_input, "left")

main_window = tk.Tk()
app = Application(main_window)
app.mainloop()
