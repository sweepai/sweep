from sweepai.utils.diff import generate_new_file_from_patch


def run_test(old_file, message):
    print(generate_new_file_from_patch(message, old_file)[0])
