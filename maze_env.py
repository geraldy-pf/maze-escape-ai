"""
maze_env.py
===========
Lingkungan (Environment) untuk simulasi "Maze Escape & Item Collector Agent".

Mengimplementasikan P.E.A.S & Problem Formulation dari slide PPT:
  - Environment : labirin grid 2D (dinding, jalan, item, start, exit tertutup/terbuka)
  - Actuators   : gerak 4-arah, ambil item (otomatis), keluar maze (otomatis saat exit terbuka)
  - Sensors     : posisi agent, deteksi dinding, status item, posisi & state pintu keluar
  - Transition  : pindah ke sel tetangga jika tidak dihalangi dinding; item otomatis
                  terkumpul saat dilewati; exit otomatis terbuka saat semua item terkumpul

PENTING -- Partially Observable (keputusan Pertimbangan #1):
  Environment TIDAK pernah memberi tahu agent seluruh isi peta sekaligus.
  Satu-satunya cara agent mendapat informasi adalah lewat method `sense()`,
  yang hanya mengembalikan sel-sel di sekitar posisi agent (radius sensor).

GIMMICK -- Teleport portal two-way (update keputusan Pertimbangan #4):
  Sepasang sel dead-end bisa dihubungkan dua arah: menginjak salah satu sisi
  langsung memindahkan agent ke sisi pasangannya, dan sebaliknya juga berlaku.
  Setiap PASANGAN portal punya identitas sendiri (`portal_pair_id`) supaya bisa
  digambar dengan warna berbeda di visualisasi. Ini murni efek environment/
  aktuator -- BFS agent TIDAK diberi tahu soal portal saat merencanakan jalur
  (lih. agent.py), agent hanya "mengalaminya" begitu benar-benar melangkah ke
  sana. Jadi algoritma pencariannya tetap Pure BFS, tidak berubah sama sekali.
"""

import random
from collections import deque

WALL, FREE = "wall", "free"


class MazeEnvironment:
    def __init__(self, grid, start, exit_pos, items, portal_pairs=None):
        """
        grid         : list[list[str]] berisi WALL/FREE, grid[r][c]
        start        : (r, c) posisi awal agent
        exit_pos     : (r, c) posisi pintu keluar
        items        : iterable (r, c) posisi awal seluruh item
        portal_pairs : list[((r,c), (r,c))] -- tiap tuple satu pasang portal DUA ARAH
        """
        self.grid = grid
        self.rows = len(grid)
        self.cols = len(grid[0])
        self.start = start
        self.exit_pos = exit_pos

        self.original_items = frozenset(items)          # ground truth lengkap, TIDAK berubah
        self.items = set(items)                          # item yang TERSISA (berkurang saat diambil)
        self.total_items = len(self.items)
        self.collected = set()
        self.exit_open = (self.total_items == 0)

        self.portal_pairs = list(portal_pairs or [])     # [(a,b), ...] -- untuk pewarnaan per pasang
        self.portals = {}                                 # lookup DUA ARAH: a->b DAN b->a
        self.portal_pair_id = {}                           # sel -> indeks pasangannya
        for idx, (a, b) in enumerate(self.portal_pairs):
            self.portals[a] = b
            self.portals[b] = a
            self.portal_pair_id[a] = idx
            self.portal_pair_id[b] = idx

    # ---------- util grid ----------
    def is_free(self, pos):
        r, c = pos
        return 0 <= r < self.rows and 0 <= c < self.cols and self.grid[r][c] == FREE

    def neighbors(self, pos):
        r, c = pos
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            np_ = (r + dr, c + dc)
            if self.is_free(np_):
                yield np_

    # ---------- ACTUATOR: efek fisik saat agent berpindah/berada di suatu sel ----------
    def visit(self, pos):
        """
        Dipanggil setiap kali agent benar-benar berada di sebuah sel (efek aktuator
        "pengambilan item otomatis"). Mengembalikan True jika item terambil di langkah ini.
        """
        picked = False
        if pos in self.items:
            self.items.remove(pos)
            self.collected.add(pos)
            picked = True
        if not self.items:
            self.exit_open = True
        return picked

    def resolve_teleport(self, pos):
        """Jika `pos` adalah salah satu sisi portal, kembalikan sel pasangannya (dua arah)."""
        return self.portals.get(pos, pos)

    # ---------- SENSOR: satu-satunya sumber informasi agent tentang dunia ----------
    def sense(self, pos, radius=1):
        """
        Mensimulasikan sensor agent (lih. P.E.A.S -> Sensors).
        Hanya sel dalam jarak Manhattan <= radius dari `pos` yang terdeteksi
        (konsisten dengan gerakan 4-arah). Ini adalah SATU-SATUNYA jalan info
        masuk ke agent -> merealisasikan sifat Partially Observable.
        """
        cells = {}
        items_detected = set()
        exit_detected = None
        portals_detected = {}
        r0, c0 = pos
        for dr in range(-radius, radius + 1):
            max_dc = radius - abs(dr)
            for dc in range(-max_dc, max_dc + 1):
                rr, cc = r0 + dr, c0 + dc
                if 0 <= rr < self.rows and 0 <= cc < self.cols:
                    t = self.grid[rr][cc]
                    cells[(rr, cc)] = t
                    if t == FREE:
                        cell = (rr, cc)
                        if cell in self.items:
                            items_detected.add(cell)
                        if cell == self.exit_pos:
                            exit_detected = (self.exit_pos, self.exit_open)
                        if cell in self.portal_pair_id:
                            portals_detected[cell] = self.portal_pair_id[cell]
        return {
            "cells": cells,
            "items_detected": items_detected,
            "exit_detected": exit_detected,
            "portals_detected": portals_detected,
        }


# ============================================================================
# GENERATOR MAZE RANDOM (dijamin solvable -- dibentuk dari spanning tree)
# ============================================================================
def generate_random_maze(rows, cols, n_items, rng=None, loop_factor=0.08):
    """
    rows, cols : ukuran maze dalam SEL LOGIS (bukan ukuran grid aktual).
    n_items    : jumlah item yang disebar.
    loop_factor: proporsi dinding ekstra yang dibuka (0 = maze pohon sempurna,
                 1 sel path unik; >0 = beberapa jalan memutar, lebih menarik
                 untuk didemonstrasikan proses eksplorasinya).

    Grid aktual berukuran (2*rows+1) x (2*cols+1): sel logis berada di indeks
    ganjil, sel genap adalah "dinding antar sel" yang bisa dibuka/ditutup.
    Dibangun dengan randomized DFS (recursive backtracker) -> otomatis solvable
    karena hasilnya adalah spanning tree yang menghubungkan semua sel logis.
    """
    rng = rng or random.Random()
    ar, ac = 2 * rows + 1, 2 * cols + 1
    grid = [[WALL] * ac for _ in range(ar)]

    def cell_to_actual(i, j):
        return 2 * i + 1, 2 * j + 1

    visited = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]
    visited[0][0] = True
    r0, c0 = cell_to_actual(0, 0)
    grid[r0][c0] = FREE

    while stack:
        i, j = stack[-1]
        options = []
        for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < rows and 0 <= nj < cols and not visited[ni][nj]:
                options.append((ni, nj, di, dj))
        if not options:
            stack.pop()
            continue
        ni, nj, di, dj = rng.choice(options)
        ar_, ac_ = cell_to_actual(i, j)
        wall_pos = (ar_ + di, ac_ + dj)
        grid[wall_pos[0]][wall_pos[1]] = FREE
        nar, nac = cell_to_actual(ni, nj)
        grid[nar][nac] = FREE
        visited[ni][nj] = True
        stack.append((ni, nj))

    # loop_factor: buka sebagian dinding tersisa agar ada rute alternatif
    if loop_factor > 0:
        candidates = []
        for i in range(rows):
            for j in range(cols):
                for di, dj, ni, nj in ((0, 1, i, j + 1), (1, 0, i + 1, j)):
                    if ni < rows and nj < cols:
                        ar_, ac_ = cell_to_actual(i, j)
                        wall_pos = (ar_ + di, ac_ + dj)
                        if grid[wall_pos[0]][wall_pos[1]] == WALL:
                            candidates.append(wall_pos)
        rng.shuffle(candidates)
        n_open = int(len(candidates) * loop_factor)
        for pos in candidates[:n_open]:
            grid[pos[0]][pos[1]] = FREE

    start = cell_to_actual(0, 0)

    # exit = sel logis terjauh dari start (BFS ground-truth, cuma dipakai saat GENERATE maze)
    dist = {start: 0}
    q = deque([start])
    env_tmp = MazeEnvironment(grid, start, start, [])
    while q:
        cur = q.popleft()
        for nb in env_tmp.neighbors(cur):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                q.append(nb)
    exit_pos = max(dist, key=dist.get)

    # sebar item di sel logis bebas (bukan start/exit)
    all_logical_free = [cell_to_actual(i, j) for i in range(rows) for j in range(cols)]
    pool = [p for p in all_logical_free if p not in (start, exit_pos)]
    rng.shuffle(pool)
    items = pool[: max(0, min(n_items, len(pool)))]

    return grid, start, exit_pos, items


def find_dead_ends(grid, exclude):
    """Sel bebas dengan TEPAT satu tetangga bebas (ujung buntu), di luar `exclude`."""
    rows, cols = len(grid), len(grid[0])

    def degree(pos):
        r, c = pos
        d = 0
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] == FREE:
                d += 1
        return d

    return [
        (r, c)
        for r in range(rows)
        for c in range(cols)
        if grid[r][c] == FREE and (r, c) not in exclude and degree((r, c)) == 1
    ]


def place_portals(grid, start, exit_pos, items, n_pairs, rng=None):
    """
    Pasang `n_pairs` portal DUA ARAH di sel dead-end (tidak menimpa start/exit/item).
    Mengembalikan list[(selA, selB), ...]; bisa lebih sedikit dari n_pairs kalau
    dead-end yang tersedia tidak cukup.
    """
    if n_pairs <= 0:
        return []
    rng = rng or random.Random()
    occupied = {start, exit_pos} | set(items)
    dead_ends = find_dead_ends(grid, occupied)
    rng.shuffle(dead_ends)

    n_pairs = min(n_pairs, len(dead_ends) // 2)
    return [(dead_ends[2 * i], dead_ends[2 * i + 1]) for i in range(n_pairs)]


def validate_maze(grid, start, exit_pos, items, portal_pairs=()):
    """
    Validasi ground-truth (HANYA dipakai saat membuat dataset, TIDAK diberikan ke agent).
    Mengecek bahwa maze benar-benar aman/solvable:
      - start, exit, semua item & portal berada di sel bebas (bukan dinding)
      - tidak ada objek yang saling menumpuk (start/exit/item/portal)
      - semua item DAN exit bisa dicapai dari start (BFS, termasuk lompatan portal)
    Mengembalikan (ok: bool, pesan: str).
    """
    rows, cols = len(grid), len(grid[0])

    def free(p):
        return 0 <= p[0] < rows and 0 <= p[1] < cols and grid[p[0]][p[1]] == FREE

    items = list(items)
    portal_cells = [c for pair in portal_pairs for c in pair]
    for name, p in [("start", start), ("exit", exit_pos)] + [("item", i) for i in items] \
            + [("portal", p) for p in portal_cells]:
        if not free(p):
            return False, f"{name} {p} berada di dinding / luar grid"

    objek = [start, exit_pos] + items + portal_cells
    if len(objek) != len(set(objek)):
        return False, "ada objek (start/exit/item/portal) yang menumpuk di sel yang sama"

    teleport = {}
    for a, b in portal_pairs:
        teleport[a], teleport[b] = b, a

    seen = {start}
    q = deque([start])
    while q:
        r, c = q.popleft()
        nexts = [(r + dr, c + dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))]
        if (r, c) in teleport:
            nexts.append(teleport[(r, c)])
        for nb in nexts:
            if nb not in seen and free(nb):
                seen.add(nb)
                q.append(nb)

    unreachable = [i for i in items if i not in seen]
    if unreachable:
        return False, f"{len(unreachable)} item tidak bisa dicapai dari start"
    if exit_pos not in seen:
        return False, "exit tidak bisa dicapai dari start"
    return True, "OK (semua item & exit bisa dicapai dari start)"


def maze_to_text(grid, start, exit_pos, items, portal_pairs=()):
    """Kebalikan load_maze_from_text: simpan maze sebagai teks (#/./S/E/I/1-9)."""
    chars = [["#" if cell == WALL else "." for cell in row] for row in grid]
    for r, c in items:
        chars[r][c] = "I"
    for idx, (a, b) in enumerate(portal_pairs[:9]):
        for r, c in (a, b):
            chars[r][c] = str(idx + 1)
    chars[start[0]][start[1]] = "S"
    chars[exit_pos[0]][exit_pos[1]] = "E"
    return "\n".join("".join(row) for row in chars) + "\n"


def load_maze_from_text(text):
    """
    Parser maze custom dari teks (opsional, untuk menguji skenario spesifik):
      '#' dinding | '.' jalan | 'S' start | 'E' exit | 'I' item (di atas sel jalan)
      '1'-'9' pasangan portal DUA ARAH: setiap digit yang muncul tepat 2 kali
      menandai sepasang sel portal yang saling terhubung.
    Mengembalikan (grid, start, exit_pos, items, portal_pairs).
    """
    lines = [ln.rstrip("\n").rstrip("\r") for ln in text.strip("\n").split("\n")]
    width = max(len(ln) for ln in lines)
    lines = [ln.ljust(width, "#") for ln in lines]

    grid = []
    start = exit_pos = None
    items = []
    portal_marks = {}
    for r, line in enumerate(lines):
        row = []
        for c, ch in enumerate(line):
            if ch == "#":
                row.append(WALL)
            else:
                row.append(FREE)
                if ch == "S":
                    start = (r, c)
                elif ch == "E":
                    exit_pos = (r, c)
                elif ch == "I":
                    items.append((r, c))
                elif ch.isdigit() and ch != "0":
                    portal_marks.setdefault(ch, []).append((r, c))
        grid.append(row)

    if start is None or exit_pos is None:
        raise ValueError("Maze custom harus punya tepat satu 'S' (start) dan satu 'E' (exit).")

    portal_pairs = [tuple(positions[:2]) for positions in portal_marks.values() if len(positions) >= 2]

    return grid, start, exit_pos, items, portal_pairs
