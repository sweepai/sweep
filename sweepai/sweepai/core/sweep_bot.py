from sweepai.sweepai.core.exceptions import UnneededEditError, MatchingError
# Other imports...

class ModifyBot:
    # Other methods...

    def some_method(self, snippet, generated_xml):
        # Some code...

        # Replace the first assert statement
        if not snippet in generated_xml:
            raise UnneededEditError("No occurrences of snippet in the generated XML.")

        # Some code...

        # Replace the second assert statement
        if not snippet:
            raise MatchingError("No more snippets after matching.")

        # Rest of the code...
