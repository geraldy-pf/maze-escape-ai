"""
agent.py
========
MazeAgent -- agen tunggal (keputusan Pertimbangan #2: Single Agent) yang
HANYA mengetahui dunia lewat sensornya sendiri (keputusan #1: Partially
Observable), dan mengambil semua keputusan jalur SEMATA-MATA lewat BFS polos
tanpa heuristic apa pun (keputusan #3: Pure BFS).

Kenapa butuh dua "mode" BFS?
-----------------------------
Karena agent tidak tahu seluruh peta sejak awal, BFS satu kali dari start ke
exit (seperti pada kasus Fully Observable) tidak bisa dilakukan -- petanya
belum lengkap. Solusinya: loop Sense -> Think -> Act setiap langkah, dengan
BFS dipakai untuk DUA tujuan berbeda, tergantung apa yang sudah diketahui:

  1. NAVIGASI : kalau target (item yang sudah diketahui, atau exit setelah
     semua item terkumpul) sudah ada di peta pengetahuan agent -> BFS cari
     jalur terpendek ke sana.
  2. EKSPLORASI : kalau belum ada target yang diketahui -> BFS cari "frontier"
     terdekat (sel bebas yang punya tetangga belum pernah disensor), lalu
     jalan ke sana untuk membuka informasi baru.

Kedua mode memakai FUNGSI BFS YANG SAMA (`self.bfs`) -- hanya goal_test yang
berbeda -- sehingga seluruh pengambilan keputusan agent murni BFS, tanpa
elemen heuristic/estimasi jarak apa pun.

Soal portal teleport dua arah (gimmick, lih. maze_env.py): BFS di sini SAMA
SEKALI tidak tahu portal itu ada -- ia merencanakan jalur hanya berdasarkan
known_map (bebas/dinding biasa). Begitu agent benar-benar melangkah ke salah
satu sisi portal, environment yang memindahkannya secara paksa ke sisi
pasangannya (lih. step()). Ini sengaja: gimmick tidak boleh mengubah
"kemurnian" algoritma BFS-nya. Konsekuensinya, sense() dipanggil setiap kali
agent TIBA di sebuah sel (lih. _arrive()), bukan cuma sekali di awal step()
-- supaya sel portal tetap sempat "dilihat" sebelum agent terlempar pergi
oleh teleport.
"""

from collections import deque


class MazeAgent:
    def __init__(self, env, vision_radius=1, max_steps=None):
        self.env = env
        self.vision_radius = vision_radius
        self.pos = env.start

        # ---- knowledge base agent (TERPISAH dari ground truth env) ----
        self.known_map = {}        # (r,c) -> 'free' / 'wall', hanya sel yg pernah disensor
        self.known_items = set()   # item yang pernah terdeteksi sensor (belum tentu terambil)
        self.collected_items = set()
        self.known_exit = None     # posisi exit, None selama belum pernah "terlihat"
        self.known_portals = {}    # (r,c) -> indeks pasangan portal, hanya yg pernah tersensor

        self.trajectory = [self.pos]
        self.log = []
        self.history = []          # snapshot tiap langkah, untuk visualisasi/animasi
        self.max_steps = max_steps or self.env.rows * self.env.cols * 4

        # agent mulai BERADA di start -> efek aktuator (bukan sensor) berlaku di sini juga
        if self.env.visit(self.pos):
            self.collected_items.add(self.pos)
        self.sense()  # sensor langsung aktif begitu agent berada di suatu sel (lih. _arrive)

    # ---------- util ----------
    def neighbors(self, pos):
        r, c = pos
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            yield (r + dr, c + dc)

    def _snapshot(self, action):
        self.history.append({
            "pos": self.pos,
            "known_map": dict(self.known_map),
            "known_items": set(self.known_items),
            "collected_items": set(self.collected_items),
            "known_exit": self.known_exit,
            "known_portals": dict(self.known_portals),
            "action": action,
        })

    # ---------- SENSE ----------
    def sense(self):
        percept = self.env.sense(self.pos, self.vision_radius)
        self.known_map.update(percept["cells"])
        self.known_items |= percept["items_detected"]
        if percept["exit_detected"] is not None:
            self.known_exit = percept["exit_detected"][0]
        self.known_portals.update(percept["portals_detected"])

    # ---------- BFS murni (tanpa heuristic) di atas known_map ----------
    def bfs(self, goal_test):
        start = self.pos
        if goal_test(start):
            return [start]
        visited = {start}
        queue = deque([start])
        parent = {}
        while queue:
            cur = queue.popleft()
            for nb in self.neighbors(cur):
                if nb in visited or self.known_map.get(nb) != "free":
                    continue
                visited.add(nb)
                parent[nb] = cur
                if goal_test(nb):
                    path = [nb]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(nb)
        return None

    def is_frontier(self, cell):
        if self.known_map.get(cell) != "free":
            return False
        return any(nb not in self.known_map for nb in self.neighbors(cell))

    # ---------- THINK: tentukan target & jalur lewat BFS ----------
    def decide(self):
        remaining_known = self.known_items - self.collected_items
        if remaining_known:
            path = self.bfs(lambda c: c in remaining_known)
            if path:
                return path, "ambil_item"

        all_collected = len(self.collected_items) == self.env.total_items
        if all_collected and self.known_exit is not None:
            path = self.bfs(lambda c: c == self.known_exit)
            if path:
                return path, "menuju_exit"

        path = self.bfs(self.is_frontier)
        if path:
            return path, "eksplorasi"

        return None, "buntu"

    def _arrive(self, cell, action):
        """
        Terapkan efek 'tiba' di sebuah sel: catat jejak, efek aktuator (ambil item),
        LALU langsung sense() dari sel itu juga.

        Sensing WAJIB dilakukan di sini (bukan cuma sekali di awal step()), karena
        kalau sel ini ternyata gerbang portal, agent akan langsung terlempar pergi
        oleh step() sebelum sempat "melihat" sekelilingnya -- tanpa baris sense()
        ini, sel gerbang portal tidak akan pernah sepenuhnya dikenali (tetangganya
        yang berupa dinding tidak pernah tersensor), sehingga is_frontier() terus
        menganggapnya belum selesai dijelajahi dan agent muter-muter ke sana lagi
        tanpa henti.
        """
        self.pos = cell
        if self.env.visit(cell):
            self.collected_items.add(cell)
        self.trajectory.append(cell)
        self.log.append({"step": len(self.trajectory) - 1, "to": cell, "action": action})
        self.sense()

    # ---------- satu siklus Sense -> Think -> Act ----------
    def step(self):
        # Tidak perlu sense() di sini -- posisi saat ini sudah tersensor sejak
        # dari __init__ atau dari _arrive() pada langkah sebelumnya.
        if (len(self.collected_items) == self.env.total_items
                and self.known_exit == self.pos):
            self._snapshot("selesai")
            return "success"

        path, action = self.decide()
        if not path or len(path) < 2:
            self._snapshot("buntu")
            return "buntu"

        next_cell = path[1]
        self._arrive(next_cell, action)

        # efek gimmick: kalau sel yang baru diinjak adalah gerbang portal, teleport paksa
        landing = self.env.resolve_teleport(next_cell)
        if landing != next_cell:
            self._arrive(landing, action + "+teleport")

        self._snapshot(self.log[-1]["action"])
        return "lanjut"

    def run(self):
        self._snapshot("mulai")
        for _ in range(self.max_steps):
            status = self.step()
            if status in ("success", "buntu"):
                return status, len(self.trajectory) - 1
        return "timeout", len(self.trajectory) - 1
