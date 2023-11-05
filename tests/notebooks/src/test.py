def a_func() -> None:
    a = 1
    b = 2 * a
    c = a * 2 + b * 3
    use_faster_model = True
    daily_ticket_count = 5
    is_paying_user = True
    ticket_count = 10
    is_consumer_tier = False
    "GPT-3.5" if use_faster_model else "GPT-4"
    payment_link = "https://sweep.dev/pricing"
    single_payment_link = "https://buy.stripe.com/00g3fh7qF85q0AE14d"
    pro_payment_link = "https://buy.stripe.com/00g5npeT71H2gzCfZ8"
    daily_message = (
        f" and {daily_ticket_count} for the day"
        if not is_paying_user and not is_consumer_tier
        else ""
    )
    "💎 <b>Sweep Pro</b>" if is_paying_user else "⚡ <b>Sweep Basic Tier</b>"
    gpt_tickets_left_message = (
        f"{ticket_count} GPT-4 tickets left for the month"
        if not is_paying_user
        else "unlimited GPT-4 tickets"
    )
    purchase_message = f"<br/><br/> For more GPT-4 tickets, visit <a href=[{single_payment_link}]>our payment portal</a>. For a one week free trial, try <a href='{pro_payment_link}'>Sweep Pro</a> (unlimited GPT-4 tickets)."
    print(b, c)
