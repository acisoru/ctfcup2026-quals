#!/usr/bin/env python3
"""Бот для snake: ведёт змейку по гамильтонову циклу до заполнения поля.

Использование: ./solve.py http://host:port  (или ws://host:port)
"""
import json
import sys

from websocket import create_connection

RADIUS = 4
# E, NE, NW, W, SW, SE - как Dirs в game.go
DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def in_board(q, r):
    return abs(q) <= RADIUS and abs(r) <= RADIUS and abs(q + r) <= RADIUS


def west(r):
    """Самая западная клетка ряда r."""
    return max(-RADIUS, -RADIUS - r)


def east(r):
    return min(RADIUS, RADIUS - r)


def hamiltonian_cycle():
    """Гамильтонов цикл по шестиугольнику радиуса 4 (61 клетка).

    Ряды r=-4..2 обходим змейкой, пропуская западную клетку каждого ряда;
    ряды 3 и 4 - вертикальным зигзагом; западный столбец - обратный путь наверх.
    """
    cycle = []
    for r in range(-RADIUS, RADIUS - 1):
        qs = list(range(west(r) + 1, east(r) + 1))
        if (r - (-RADIUS)) % 2 == 1:
            qs.reverse()
        cycle += [(q, r) for q in qs]
    # зигзаг по рядам 3 и 4: (1,3) (0,4) (0,3) (-1,3) (-1,4) (-2,4) (-2,3) (-3,3) (-3,4) (-4,4)
    cycle += [(1, 3), (0, 4), (0, 3), (-1, 3), (-1, 4), (-2, 4), (-2, 3), (-3, 3), (-3, 4), (-4, 4)]
    # западный столбец снизу вверх
    cycle += [(west(r), r) for r in range(RADIUS - 1, -RADIUS - 1, -1)]

    cells = {(q, r) for q in range(-RADIUS, RADIUS + 1) for r in range(-RADIUS, RADIUS + 1) if in_board(q, r)}
    assert set(cycle) == cells and len(cycle) == len(cells), "цикл не покрывает поле"
    for a, b in zip(cycle, cycle[1:] + cycle[:1]):
        assert (b[0] - a[0], b[1] - a[1]) in DIRS, f"{a} -> {b} не соседи"
    return cycle


CYCLE = hamiltonian_cycle()
N = len(CYCLE)
INDEX = {c: i for i, c in enumerate(CYCLE)}


def forward(a, b):
    """Расстояние по циклу от a до b по ходу движения, в (0, N]."""
    d = (INDEX[b] - INDEX[a]) % N
    return d if d else N


def choose_dir(state):
    head = (state["snake"][0]["q"], state["snake"][0]["r"])
    tail = (state["snake"][-1]["q"], state["snake"][-1]["r"])
    food = (state["food"]["q"], state["food"]["r"])

    # Тело всегда лежит на дуге цикла позади головы, поэтому любая клетка,
    # которая по ходу цикла ближе к голове, чем хвост, свободна; сам хвост
    # на этом ходу уезжает, на него тоже можно. Среди соседей выбираем самый
    # далёкий по циклу, не перепрыгивая еду.
    d_tail = forward(head, tail) if len(state["snake"]) > 1 else N
    d_food = forward(head, food)
    best, best_d = None, -1
    for i, (dq, dr) in enumerate(DIRS):
        nxt = (head[0] + dq, head[1] + dr)
        if not in_board(*nxt):
            continue
        d = forward(head, nxt)
        if d <= d_tail and d <= d_food and d > best_d:
            best, best_d = i, d
    assert best is not None  # следующая клетка цикла подходит всегда
    return best


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    url = base.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"
    ws = create_connection(url, timeout=30)
    state = json.loads(ws.recv())
    if state["won"] or not state["alive"]:
        ws.send(json.dumps({"type": "reset"}))
        state = json.loads(ws.recv())

    moves = 0
    while not state["won"]:
        assert state["alive"], "змейка умерла"
        ws.send(json.dumps({"type": "move", "dir": choose_dir(state)}))
        state = json.loads(ws.recv())
        moves += 1
        if moves % 100 == 0:
            print(f"[+] moves={moves} length={state['length']}/{state['target']}", file=sys.stderr)

    print(f"[+] done in {moves} moves, length={state['length']}", file=sys.stderr)
    print(state["message"])


if __name__ == "__main__":
    main()
