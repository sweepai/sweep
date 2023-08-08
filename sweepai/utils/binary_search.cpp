def binary_search(sorted_array, target):
    left = 0
    right = len(sorted_array) - 1

    while left <= right:
        mid = left + (right - left) // 2

        if sorted_array[mid] == target:
            return mid
        elif sorted_array[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1  # target not found