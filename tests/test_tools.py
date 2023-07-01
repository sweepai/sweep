import os
import anthropic
from src.core.react import REACT_RESPONSE_PROMPT, ReadFiles, Finish, Toolbox

tictactoe_response = """
class TicTacToe:
    def __init__(self):
        self.board = [
            ["-", "-", "-"],
            ["-", "-", "-"],
            ["-", "-", "-"]
        ]
        self.current_player = "X"

    def make_move(self, row, col):
        if self.board[row][col] == "-":
            self.board[row][col] = self.current_player
            self.current_player = "O" if self.current_player == "X" else "X"
        else:
            print("Invalid move")

    def check_winner(self):
        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2] != "-":
                return self.board[i][0]
            if self.board[0][i] == self.board[1][i] == self.board[2][i] != "-":
                return self.board[0][i]
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != "-":
            return self.board[0][0]
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != "-":
            return self.board[0][2]
        if all([cell != "-" for row in self.board for cell in row]):
            return "Tie"
        return None
"""


@ReadFiles.tool()
def file_search(query: str):
    # return open(query, "r").read()
    return tictactoe_response


@Finish.tool()
def finish(query: str):
    return ""


example_google_problem = """
<snippet file="model.py">
import torch
import torch.nn as nn
import torch.nn.functional as F


class Net(nn.Module):

    def __init__(self):
        super(Net, self).__init__()
        # 1 input image channel, 6 output channels, 5x5 square convolution
        # kernel
        self.conv1 = nn.Conv2d(1, 6, 5)
        self.conv2 = nn.Conv2d(6, 16, 5)
        # an affine operation: y = Wx + b
        self.fc1 = nn.Linear(16 * 5 * 5, 120)  # 5*5 from image dimension
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x):
        # Max pooling over a (2, 2) window
        x = F.max_pool2d(F.relu(self.conv1(x)), (2, 2))
        # If the size is a square, you can specify with a single number
        x = F.max_pool2d(F.relu(self.conv2(x)), 2)
        x = torch.flatten(x, 1) # flatten all dimensions except the batch dimension
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x


net = Net()
print(net)
</snippet>

<comment username="kevinlu1248">
Can we use tensorflow instead?
</comment>
"""

example_file_search_problem = """
<file path="tests/tictactoe.py">
from src.tictactoe import TicTacToe

t = TicTacToe()
t.play()
</file>

<comment username="kevinlu1248">
This is erroring out. Can you fix it?
</comment>
"""

if __name__ == "__main__":
    toolbox = Toolbox(tools=[file_search, finish])
    prompt = example_file_search_problem + toolbox.prompt
    client = anthropic.Client(os.environ.get("ANTHROPIC_API_KEY"))

    current_prompt = anthropic.HUMAN_PROMPT + prompt + anthropic.AI_PROMPT
    for _ in range(5):
        print("Prompt:" + current_prompt)
        response = client.completion(
            prompt=current_prompt,
            stop_sequences=[anthropic.HUMAN_PROMPT],
            model="claude-v1.3",
            max_tokens_to_sample=1024,
        )["completion"]
        parsed_results = Toolbox.ParsedResults.parse(response)
        if parsed_results.tool_name == "Finish":
            break
        result = toolbox.process_results(parsed_results)
        current_prompt = (
            current_prompt
            + response
            + anthropic.HUMAN_PROMPT
            + REACT_RESPONSE_PROMPT.format(output=result)
            + anthropic.AI_PROMPT
        )
    else:
        raise Exception("Too many attempts")
    print("Done!")
