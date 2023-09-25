from sweepai.exceptions import UnneededEditError, MatchingError

class ModifyBot:
    def __init__(self, xml, snippet):
        self.xml = xml
        self.snippet = snippet

    def modify(self):
        # Identify the first assert statement and replace it
        if not self.snippet in self.xml:
            raise UnneededEditError("Snippet not found in XML")

        # Rest of the code...

        # Identify the second assert statement and replace it
        if not self.snippet:
            raise MatchingError("No more snippets left")

        # Rest of the code...
