# Two-pointer pair-sum on a sorted array. Locals `i` and `j` close in from
# the ends until they meet or find a pair. The visualizer should overlay
# the active [i..j] range and animate the convergence.

def pair_sum_sorted(nums, target):
    i = 0
    j = len(nums) - 1
    while i < j:
        s = nums[i] + nums[j]
        if s == target:
            return [i, j]
        if s < target:
            i += 1
        else:
            j -= 1
    return [-1, -1]


if __name__ == "__main__":
    print(pair_sum_sorted([1, 2, 4, 7, 11, 15], 15))
