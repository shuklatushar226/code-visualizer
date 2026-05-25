# BFS over an adjacency-dict graph. The visualizer auto-detects the dict
# of lists as a graph and the deque-ish list as a queue.

# @viz:graph=graph
# @viz:queue=queue
# @viz:visited=set

from collections import deque


def bfs(graph, start):
    visited = set([start])
    queue = deque([start])
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nb in graph[node]:
            if nb not in visited:
                visited.add(nb)
                queue.append(nb)
    return order


if __name__ == "__main__":
    graph = {
        "A": ["B", "C"],
        "B": ["A", "D", "E"],
        "C": ["A", "F"],
        "D": ["B"],
        "E": ["B", "F"],
        "F": ["C", "E"],
    }
    print(bfs(graph, "A"))
