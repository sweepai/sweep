class SweepBot:
    ...
    def has_changes(self, file_change_requests, branch_name):
        # Compare the current state of the files with the proposed changes
        for request in file_change_requests:
            current_file = self.repo.get_contents(request.filename, ref=branch_name)
            if current_file.decoded_content.decode("utf-8") != request.instructions:
                return True
        return False
