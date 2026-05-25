# Classic two-sum: return indices of two numbers that add up to target.
# Great first demo because the dict `seen` is updated every iteration,
# so the visualizer shows a growing hashmap and a moving "i" pointer.

def two_sum(nums, target):
    seen = {}  # value -> index
    for i, x in enumerate(nums):
        need = target - x
        if need in seen:
            return [seen[need], i]
        seen[x] = i
    return []


if __name__ == "__main__":
    nums = [2, 7, 11, 15]
    target = 9
    print(two_sum(nums, target))
