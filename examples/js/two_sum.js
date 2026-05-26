// Classic two-sum, JavaScript edition. Mirrors examples/python/two_sum.py
// so a JS trace renders the same dict-growth + moving-i story in the panel.

function twoSum(nums, target) {
    const seen = {};                 // value -> index
    for (let i = 0; i < nums.length; i++) {
        const x = nums[i];
        const need = target - x;
        if (need in seen) {
            return [seen[need], i];
        }
        seen[x] = i;
    }
    return [];
}

console.log(twoSum([2, 7, 11, 15], 9));
