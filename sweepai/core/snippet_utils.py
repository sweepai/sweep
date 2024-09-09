def convert_lines_to_and_merge_ranges(
    lines: list[int],
    range_size: int = 10,
    lower_bound: int = -1,
    upper_bound: int = -1,
    offset: int = 0, # offset to apply to each line number
) -> list[tuple[int, int]]:
    """
    Converts a list of line numbers to a list of ranges, handles merging of ranges with custom range_size
    """
    if not lines:
        return []
    ranges = []
    lines.sort()
    range_size = max(0, range_size) # ensure at least one line is present
    for line in lines:
        if offset:
            line += offset
        start = max(0, line - range_size)
        end = line + range_size
        if lower_bound != -1:
            start = max(start, lower_bound)
        if upper_bound != -1:
            end = min(end, upper_bound)
        if not ranges:
            ranges.append((start, end))
        else:
            # check if we need to merge the ranges
            previous_start, previous_end = ranges[-1]
            if start <= previous_end:
                ranges[-1] = (previous_start, end)
            else:
                ranges.append((start, end))
    return ranges


def merge_snippet_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Merges overlapping ranges
    """
    if not ranges:
        return []
    ranges.sort()
    merged_ranges = [ranges[0]]
    for current_start, current_end in ranges[1:]:
        previous_start, previous_end = merged_ranges[-1]
        if current_start <= previous_end:
            merged_ranges[-1] = (previous_start, max(previous_end, current_end))
        else:
            merged_ranges.append((current_start, current_end))
    return merged_ranges