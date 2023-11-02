pr = object()
pr.html_url = ""
center = lambda x: x
payment_message_start = "test"


def a_func():
    a = 1
    b = 2 * a
    c = a * 2 + b * 3
    f"test [{pr.html_url}]({pr.html_url}).\n{center(payment_message_start)}"
    print(b, c)
