def minimum_apple_cost(num_supermarkets, num_apples, supermarkets):
    # Sort the supermarkets by price per kilo in ascending order
    supermarkets.sort(key=lambda x: x[0] / x[1])

    # Initialize the minimum cost to a large number
    min_cost = float('inf')

    # Iterate over the supermarkets
    for i in range(num_supermarkets):
        # Calculate the cost of buying the needed apples from this supermarket
        cost = 0
        apples_needed = num_apples
        for j in range(i, num_supermarkets):
            can_buy = min(apples_needed, supermarkets[j][1])
            cost += can_buy * supermarkets[j][0]
            apples_needed -= can_buy
            if apples_needed == 0:
                break

        # Update the minimum cost
        min_cost = min(min_cost, cost)

    return min_cost