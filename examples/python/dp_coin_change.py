# Classic tabulation DP: minimum coins to make `amount`.
# `dp[i]` is the min coins for amount i; cells fill in strict index order,
# so the DP detector should fire on the `dp` local.

def coin_change(coins, amount):
    INF = amount + 1
    dp = [INF] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        best = INF
        for c in coins:
            if c <= i and dp[i - c] + 1 < best:
                best = dp[i - c] + 1
        dp[i] = best
    return -1 if dp[amount] >= INF else dp[amount]


if __name__ == "__main__":
    print(coin_change([1, 2, 5], 11))
