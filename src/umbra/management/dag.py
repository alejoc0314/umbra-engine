"""Dependencias entre tareas: grafo dirigido acíclico (Kahn, O(V + E))."""

from collections import defaultdict, deque


class CycleError(Exception):
    pass


def topo_order(nodes, edges) -> list:
    """edges: (tarea, depende_de). Devuelve un orden donde cada dependencia va antes."""
    nodes = list(nodes)
    indegree = {n: 0 for n in nodes}
    after = defaultdict(list)
    for task, dep in edges:
        if task not in indegree or dep not in indegree:
            raise KeyError(f"dependencia con tarea inexistente: {task} -> {dep}")
        after[dep].append(task)
        indegree[task] += 1
    queue = deque(n for n in nodes if indegree[n] == 0)
    order = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for m in after[n]:
            indegree[m] -= 1
            if indegree[m] == 0:
                queue.append(m)
    if len(order) != len(nodes):
        cyclic = sorted(str(n) for n in nodes if indegree[n] > 0)
        raise CycleError(f"ciclo de dependencias entre: {', '.join(cyclic)}")
    return order
