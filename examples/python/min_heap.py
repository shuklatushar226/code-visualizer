# Manual min-heap operations on a plain list. The visualizer's
# HeapTreeView will render the array as a complete binary tree using
# 2i+1 / 2i+2 index math.

# @viz:heap=heap


def sift_up(heap, i):
    while i > 0:
        parent = (i - 1) // 2
        if heap[i] < heap[parent]:
            heap[i], heap[parent] = heap[parent], heap[i]
            i = parent
        else:
            return


def sift_down(heap, i):
    n = len(heap)
    while True:
        l = 2 * i + 1
        r = 2 * i + 2
        smallest = i
        if l < n and heap[l] < heap[smallest]:
            smallest = l
        if r < n and heap[r] < heap[smallest]:
            smallest = r
        if smallest == i:
            return
        heap[i], heap[smallest] = heap[smallest], heap[i]
        i = smallest


def push(heap, x):
    heap.append(x)
    sift_up(heap, len(heap) - 1)


def pop_min(heap):
    top = heap[0]
    last = heap.pop()
    if heap:
        heap[0] = last
        sift_down(heap, 0)
    return top


if __name__ == "__main__":
    heap = []
    for x in [5, 3, 8, 1, 9, 2, 7]:
        push(heap, x)
    out = []
    while heap:
        out.append(pop_min(heap))
    print(out)  # sorted ascending
