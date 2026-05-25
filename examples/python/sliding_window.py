# Longest substring without repeating characters, sliding-window flavour.
# Locals `l` and `r` move forward over `s`; the visualizer should overlay
# the active window [l..r] on the rendered string.

def length_of_longest_substring(s):
    seen = {}
    l = 0
    best = 0
    for r in range(len(s)):
        ch = s[r]
        if ch in seen and seen[ch] >= l:
            l = seen[ch] + 1
        seen[ch] = r
        if r - l + 1 > best:
            best = r - l + 1
    return best


if __name__ == "__main__":
    print(length_of_longest_substring("abcabcbb"))
