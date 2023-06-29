class CodeRepairer:
    def check_syntax(self, code):
        try:
            compile(code, '<string>', 'exec')
            return True
        except SyntaxError:
            return False

    def repair_code(self, code):
        if self.check_syntax(code):
            return code
        else:
            return None

