from exceptions import UnneededEditError, MatchingError

class ModifyBot:
    def __init__(self, snippets, xml):
        self.snippets = snippets
        self.xml = xml

    def modify(self):
        # Identify the assert statement that checks if there are no occurrences of the snippet in the generated XML.
        # Replace this assert statement with a raise statement that raises an UnneededEditError with a descriptive message.
        if not self.snippets in self.xml:
            raise UnneededEditError("No occurrences of the snippet in the generated XML")

        # Identify the assert statement that checks if there are no more snippets after matching.
        # Replace this assert statement with a raise statement that raises a MatchingError with a descriptive message.
        if not self.snippets:
            raise MatchingError("No more snippets after matching")
