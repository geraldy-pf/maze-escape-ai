"""
main.py
=======
Entry point simulasi "Maze Escape & Item Collector Agent Berbasis BFS".

Contoh pemakaian:
    python main.py
    python main.py --rows 12 --cols 12 --items 6 --seed 42 --animate
    python main.py --maze-file contoh_maze.txt --animate
    python main.py --fully-observable        # eksperimen: matikan Partially Observable
    python main.py --portals 0               # matikan gimmick teleport portal
"""

import argparse
import os
import random

from maze_env import MazeEnvironment, generate_random_maze, load_maze_from_text, place_portals
from agent import MazeAgent
from visualize import plot_final_result, make_animation


def print_known_map(agent, env):
    """Representasi teks sederhana dari peta yang SUDAH diketahui agent saat ini.
    Angka (0-9) = sel portal diketahui, menunjukkan indeks pasangannya (portal
    dua arah -- dua sel dengan angka sama = satu pasang, saling terhubung)."""
    lines = []
    for r in range(env.rows):
        row = ""
        for c in range(env.cols):
            cell = (r, c)
            if cell == agent.pos:
                row += "A"
            elif cell == env.start:
                row += "S"
            elif cell == agent.known_exit:
                row += "E"
            elif cell in agent.known_items - agent.collected_items:
                row += "*"
            elif cell in agent.known_portals:
                pid = agent.known_portals[cell]
                row += str(pid % 10)
            elif agent.known_map.get(cell) == "wall":
                row += "#"
            elif agent.known_map.get(cell) == "free":
                row += "."
            else:
                row += " "  # belum pernah tersensor
        lines.append(row)
    print("\n".join(lines))


def build_parser():
    p = argparse.ArgumentParser(description="Simulasi Maze Escape & Item Collector Agent (BFS)")
    p.add_argument("--rows", type=int, default=10, help="jumlah baris sel logis maze (default 10)")
    p.add_argument("--cols", type=int, default=10, help="jumlah kolom sel logis maze (default 10)")
    p.add_argument("--items", type=int, default=5, help="jumlah item yang disebar (default 5)")
    p.add_argument("--vision", type=int, default=1,
                    help="radius sensor agent dalam langkah Manhattan (default 1 = tetangga langsung)")
    p.add_argument("--loop", type=float, default=0.08,
                    help="proporsi dinding ekstra yang dibuka agar ada rute memutar (default 0.08)")
    p.add_argument("--portals", type=int, default=2,
                    help="jumlah pasang portal teleport dua arah di dead-end (default 2, 0 = nonaktif)")
    p.add_argument("--seed", type=int, default=None, help="seed random agar hasil bisa direproduksi")
    p.add_argument("--maze-file", type=str, default=None,
                    help="path file teks maze custom (#/./S/E/I/1-9), menggantikan maze random")
    p.add_argument("--fully-observable", action="store_true",
                    help="eksperimen: paksa agent langsung tahu seluruh peta (vision radius maksimum)")
    p.add_argument("--animate", action="store_true", help="simpan juga animasi GIF proses eksplorasi")
    p.add_argument("--outdir", type=str, default="output", help="folder output gambar/gif")
    return p


def main():
    args = build_parser().parse_args()
    rng = random.Random(args.seed)

    if args.maze_file:
        with open(args.maze_file, "r", encoding="utf-8") as f:
            grid, start, exit_pos, items, portal_pairs = load_maze_from_text(f.read())
    else:
        grid, start, exit_pos, items = generate_random_maze(
            args.rows, args.cols, args.items, rng=rng, loop_factor=args.loop
        )
        portal_pairs = place_portals(grid, start, exit_pos, items, args.portals, rng=rng)

    env = MazeEnvironment(grid, start, exit_pos, items, portal_pairs=portal_pairs)
    vision_radius = (env.rows + env.cols) if args.fully_observable else args.vision
    agent = MazeAgent(env, vision_radius=vision_radius)

    gimmick_desc = (f"teleport portal dua arah ({len(env.portal_pairs)} pasang)"
                     if env.portal_pairs else "belum ada")

    print("=" * 62)
    print(" SIMULASI: Maze Escape & Item Collector Agent (BFS)")
    print("=" * 62)
    print(f" Ukuran grid aktual   : {env.rows} x {env.cols}")
    print(f" Jumlah item          : {env.total_items}")
    print(f" Start -> Exit        : {env.start} -> {env.exit_pos}")
    print(" Keputusan Pertimbangan:")
    print(f"   1. Observability    : {'Fully' if args.fully_observable else 'Partially'} Observable"
          f" (radius sensor = {vision_radius})")
    print("   2. Jumlah agent     : Single Agent")
    print("   3. Algoritma        : Pure BFS (tanpa heuristic)")
    print(f"   4. Elemen tambahan  : {gimmick_desc}")
    print("-" * 62)

    status, n_steps = agent.run()

    for entry in agent.log:
        print(f" Langkah {entry['step']:>3} -> pindah ke {entry['to']} "
              f"| aksi: {entry['action']}")

    print("-" * 62)
    if status == "success":
        print(f" HASIL: BERHASIL keluar labirin dalam {n_steps} langkah, "
              f"{len(agent.collected_items)}/{env.total_items} item terkumpul.")
    elif status == "buntu":
        print(f" HASIL: BUNTU setelah {n_steps} langkah -- tidak ada area tersisa "
              f"untuk dijelajahi (maze mungkin tidak solvable dari sini).")
    else:
        print(f" HASIL: TIMEOUT setelah {n_steps} langkah (melebihi batas {agent.max_steps}).")

    print("\n Peta yang diketahui agent pada akhir simulasi:")
    print_known_map(agent, env)

    os.makedirs(args.outdir, exist_ok=True)
    final_png = os.path.join(args.outdir, "hasil_akhir.png")
    plot_final_result(env, agent, final_png)
    print(f"\n Visualisasi akhir disimpan di: {final_png}")

    if args.animate:
        gif_path = os.path.join(args.outdir, "simulasi.gif")
        make_animation(env, agent, gif_path)
        print(f" Animasi proses eksplorasi disimpan di: {gif_path}")


if __name__ == "__main__":
    main()
