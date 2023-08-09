class SnakeGame:
    def __init__(self, initial_state):
        self.game_state = initial_state
        self.snake_position = self.game_state.get('snake_position', [])

    def initialize(self):
        # Initialize the game state
        self.game_state = {'snake_position': [(0, 0)], 'remaining_contributions': {}}

    def make_move(self, direction):
        # Update the position of the snake according to the move direction
        x, y = self.game_state['snake_position'][-1]
        if direction == 'up':
            self.game_state['snake_position'].append((x, y-1))
        elif direction == 'down':
            self.game_state['snake_position'].append((x, y+1))
        elif direction == 'left':
            self.game_state['snake_position'].append((x-1, y))
        elif direction == 'right':
            self.game_state['snake_position'].append((x+1, y))
        # Return the new game state
        return self.game_state

    def check_eaten(self):
        # Check if the snake's new position corresponds to a contribution
        if self.game_state['snake_position'][-1] in self.game_state['remaining_contributions']:
            # If it does, reduce the corresponding contribution and return True
            self.game_state['remaining_contributions'][self.game_state['snake_position'][-1]] -= 1
            return True
        # Otherwise, return False
        return False