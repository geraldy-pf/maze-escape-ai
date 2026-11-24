"""
batch_run.py
============
Menjalankan BANYAK percobaan (default 200) sekaligus, masing-masing dengan maze
(dataset) yang BERBEDA, dan menyimpan hasil tiap percobaan di foldernya sendiri:

    output/
    ├── percobaan_001/
    │   ├── hasil_akhir.png   # visualisasi akhir (ground truth + peta agent)
    │   ├── simulasi.gif      # animasi proses eksplorasi
    │   ├── maze.txt          # dataset maze-nya (bisa diputar ulang: main.py --maze-file)
    │   └── log.txt           # info maze, trace langkah, peta ASCII agent
    ├── percobaan_002/
    ├── ...
    └── ringkasan.csv         # rekap semua percobaan (seed, langkah, status, dll.)

Jaminan keamanan dataset:
  1. Maze dibangun dari spanning tree (randomized DFS) -> semua sel terhubung.
  2. Tiap maze DIVALIDASI ulang (validate_maze): item & exit pasti bisa dicapai.
  3. Tiap maze dicek UNIK (sidik jari grid+start+exit+item+portal): tidak ada
     dua percobaan dengan maze yang sama. Kalau duplikat/invalid -> seed dilewati.

Contoh:
    python batch_run.py                          # 200 percobaan, ukuran default 10x10
    python batch_run.py --n 200 --vary-size      # ukuran & jumlah item ikut diacak
    python batch_run.py --n 10 --no-gif          # cepat, tanpa GIF
    python batch_run.py --workers 4              # atur jumlah proses paralel
"""

import argparse
import csv
import hashlib
import os
import random
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from maze_env import (MazeEnvironment, generate_random_maze, place_portals,
                      validate_maze, maze_to_text)
from agent import MazeAgent


def known_map_text(agent, env):
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
                row += str(agent.known_portals[cell] % 10)
            elif agent.known_map.get(cell) == "wall":
                row += "#"
            elif agent.known_map.get(cell) == "free":
                row += "."
            else:
                row += " "
        lines.append(row)
    return "\n".join(lines)


def fingerprint(grid, start, exit_pos, items, portal_pairs):
    portals = sorted(tuple(sorted(p)) for p in portal_pairs)
    raw = repr((grid, start, exit_pos, sorted(items), portals))
    return hashlib.sha1(raw.encode()).hexdigest()


def build_datasets(args):
    """Buat N maze unik & tervalidasi (cepat, di proses utama)."""
    datasets, seen = [], set()
    seed = args.start_seed
    skipped = 0
    while len(datasets) < args.n:
        rng = random.Random(seed)
        if args.vary_size:
            rows = rng.randint(args.min_size, args.max_size)
            cols = rng.randint(args.min_size, args.max_size)
            n_items = rng.randint(args.min_items, args.max_items)
        else:
            rows, cols, n_items = args.rows, args.cols, args.items
        grid, start, exit_pos, items = generate_random_maze(rows, cols, n_items, rng=rng,
                                                            loop_factor=args.loop)
        portal_pairs = place_portals(grid, start, exit_pos, items, args.portals, rng=rng)

        ok, _ = validate_maze(grid, start, exit_pos, items, portal_pairs)
        fp = fingerprint(grid, start, exit_pos, items, portal_pairs)
        if ok and fp not in seen:
            seen.add(fp)
            datasets.append({
                "no": len(datasets) + 1, "seed": seed, "rows": rows, "cols": cols,
                "grid": grid, "start": start, "exit": exit_pos, "items": items,
                "portals": portal_pairs, "fingerprint": fp,
            })
        else:
            skipped += 1
        seed += 1
    return datasets, skipped


def run_one(ds, args):
    """Jalankan 1 percobaan + simpan semua output ke foldernya sendiri."""
    from visualize import plot_final_result, make_animation  # import di worker

    t0 = time.time()
    folder = os.path.join(args.outdir, f"percobaan_{ds['no']:03d}")
    os.makedirs(folder, exist_ok=True)

    env = MazeEnvironment(ds["grid"], ds["start"], ds["exit"], ds["items"],
                          portal_pairs=ds["portals"])
    vision = (env.rows + env.cols) if args.fully_observable else args.vision
    agent = MazeAgent(env, vision_radius=vision)
    status, n_steps = agent.run()
    n_teleport = sum(1 for e in agent.log if e["action"].endswith("+teleport"))

    with open(os.path.join(folder, "maze.txt"), "w", encoding="utf-8") as f:
        f.write(maze_to_text(ds["grid"], ds["start"], ds["exit"], ds["items"], ds["portals"]))

    with open(os.path.join(folder, "log.txt"), "w", encoding="utf-8") as f:
        f.write(f"PERCOBAAN {ds['no']}\n")
        f.write(f"Seed            : {ds['seed']}\n")
        f.write(f"Sidik jari maze : {ds['fingerprint']}\n")
        f.write(f"Ukuran logis    : {ds['rows']} x {ds['cols']} (grid aktual {env.rows} x {env.cols})\n")
        f.write(f"Jumlah item     : {env.total_items}\n")
        f.write(f"Portal          : {len(env.portal_pairs)} pasang\n")
        f.write(f"Start -> Exit   : {env.start} -> {env.exit_pos}\n")
        f.write(f"Observability   : {'Fully' if args.fully_observable else 'Partially'} (radius {vision})\n")
        f.write("-" * 60 + "\n")
        for e in agent.log:
            f.write(f"Langkah {e['step']:>4} -> {e['to']} | aksi: {e['action']}\n")
        f.write("-" * 60 + "\n")
        f.write(f"HASIL: {status.upper()} | langkah: {n_steps} | item: "
                f"{len(agent.collected_items)}/{env.total_items} | teleport: {n_teleport}\n\n")
        f.write("Peta yang diketahui agent di akhir:\n")
        f.write(known_map_text(agent, env) + "\n")

    plot_final_result(env, agent, os.path.join(folder, "hasil_akhir.png"))
    if not args.no_gif:
        make_animation(env, agent, os.path.join(folder, "simulasi.gif"))

    known_free = sum(1 for t in agent.known_map.values() if t == "free")
    total_free = sum(row.count("free") for row in env.grid)
    return {
        "percobaan": ds["no"], "seed": ds["seed"], "rows": ds["rows"], "cols": ds["cols"],
        "items": env.total_items, "portals": len(env.portal_pairs), "status": status,
        "langkah": n_steps, "item_terkumpul": len(agent.collected_items),
        "teleport": n_teleport,
        "persen_peta_diketahui": round(100 * known_free / total_free, 1),
        "durasi_detik": round(time.time() - t0, 2), "fingerprint": ds["fingerprint"],
    }


def build_parser():
    p = argparse.ArgumentParser(description="Batch banyak percobaan Maze Escape BFS")
    p.add_argument("--n", type=int, default=200, help="jumlah percobaan (default 200)")
    p.add_argument("--rows", type=int, default=10)
    p.add_argument("--cols", type=int, default=10)
    p.add_argument("--items", type=int, default=5)
    p.add_argument("--portals", type=int, default=2)
    p.add_argument("--vision", type=int, default=1)
    p.add_argument("--loop", type=float, default=0.08)
    p.add_argument("--vary-size", action="store_true",
                   help="acak ukuran maze & jumlah item tiap percobaan")
    p.add_argument("--min-size", type=int, default=8)
    p.add_argument("--max-size", type=int, default=14)
    p.add_argument("--min-items", type=int, default=3)
    p.add_argument("--max-items", type=int, default=8)
    p.add_argument("--start-seed", type=int, default=1, help="seed awal (default 1)")
    p.add_argument("--fully-observable", action="store_true")
    p.add_argument("--no-gif", action="store_true", help="lewati pembuatan GIF (jauh lebih cepat)")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                   help="jumlah proses paralel")
    p.add_argument("--outdir", type=str, default="output")
    p.add_argument("--clean", action="store_true",
                   help="hapus folder percobaan_* lama di outdir sebelum mulai")
    return p


def main():
    args = build_parser().parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    if args.clean:
        for name in os.listdir(args.outdir):
            if name.startswith("percobaan_"):
                shutil.rmtree(os.path.join(args.outdir, name), ignore_errors=True)

    print(f"Membuat {args.n} dataset maze unik & tervalidasi...")
    datasets, skipped = build_datasets(args)
    print(f"  -> {len(datasets)} maze unik siap (seed {datasets[0]['seed']}..{datasets[-1]['seed']}, "
          f"{skipped} dilewati karena duplikat/invalid)")
    print(f"Menjalankan simulasi dengan {args.workers} proses paralel "
          f"({'tanpa' if args.no_gif else 'dengan'} GIF)...\n")

    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(run_one, ds, args): ds["no"] for ds in datasets}
        for i, fut in enumerate(as_completed(futures), 1):
            no = futures[fut]
            try:
                r = fut.result()
                results.append(r)
                print(f"[{i:>3}/{len(datasets)}] percobaan_{no:03d}: {r['status']:<8} "
                      f"{r['langkah']:>4} langkah, item {r['item_terkumpul']}/{r['items']} "
                      f"({r['durasi_detik']}s)")
            except Exception as e:  # jangan hentikan batch karena 1 percobaan error
                print(f"[{i:>3}/{len(datasets)}] percobaan_{no:03d}: ERROR {e!r}")
                results.append({"percobaan": no, "status": f"error: {e!r}"})

    results.sort(key=lambda r: r["percobaan"])
    fields = ["percobaan", "seed", "rows", "cols", "items", "portals", "status", "langkah",
              "item_terkumpul", "teleport", "persen_peta_diketahui", "durasi_detik", "fingerprint"]
    csv_path = os.path.join(args.outdir, "ringkasan.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    ok = [r for r in results if r.get("status") == "success"]
    print("\n" + "=" * 60)
    print(f" SELESAI dalam {time.time() - t0:.1f} detik")
    print(f" Berhasil : {len(ok)}/{len(results)} percobaan")
    if ok:
        steps = [r["langkah"] for r in ok]
        print(f" Langkah  : rata-rata {sum(steps) / len(steps):.1f}, min {min(steps)}, max {max(steps)}")
    print(f" Rekap    : {csv_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
