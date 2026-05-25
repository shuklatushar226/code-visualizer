# Standard binary search. Locals `lo`, `hi`, `mid` shrink the search range
# in half each iteration. The visualizer should highlight [lo..hi] with
# `mid` marked, and the range should visibly halve over successive steps.

def binary_search(nums, target):
    lo = 0
    hi = len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        if nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


if __name__ == "__main__":
    print(binary_search([1, 3, 5, 7, 9, 11, 13, 15, 17, 19], 13))
