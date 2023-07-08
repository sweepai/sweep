class NewFeature:
    def __init__(self):
        # Initialize necessary variables
        self.variable = None

    def execute_feature(self):
        # Implement the core functionality of the new feature
        # Use the helper function if necessary
        result = self.helper_func(self.variable)
        return result

    def helper_func(self, variable):
        # Assist the main function in performing its task
        # For example, perform some calculation on the variable
        result = variable * 2
        return result