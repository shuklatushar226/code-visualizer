# Backtracking permutations. The recursion tree fans out by len(remaining)
# at each level, so for n=3 there are 1 + 3 + 6 + 6 = 16 frames — small
# enough to render comfortably and big enough to show the branching shape.

def permutations(nums):
    out = []

    def backtrack(path, remaining):
        if not remaining:
            out.append(path[:])
            return
        for i in range(len(remaining)):
            path.append(remaining[i])
            backtrack(path, remaining[:i] + remaining[i + 1:])
            path.pop()

    backtrack([], nums)
    return out


if __name__ == "__main__":
    print(permutations([1, 2, 3]))
