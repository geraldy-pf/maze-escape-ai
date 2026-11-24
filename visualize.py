"""
visualize.py
============
Memenuhi Tujuan #3 di PPT: "Memvisualisasikan proses pencarian serta jalur
yang ditempuh agen". Dua output:

  1. plot_final_result() -> PNG statis, dua panel:
       kiri  = peta SEBENARNYA (ground truth) + seluruh jejak langkah agent
       kanan = peta yang BERHASIL DIKETAHUI agent di akhir simulasi
               (sel abu-abu = belum pernah tersensor -> bukti ia bekerja
               tanpa tahu seluruh peta sejak awal / Partially Observable)

  2. make_animation() -> GIF animasi, menunjukkan knowledge map terbuka
     sedikit demi sedikit seiring agent bergerak (opsional, --animate).

Simbol:
  - Start  : kotak hijau
  - Exit   : bentuk pintu (persegi panjang vertikal + atap melengkung),
             coklat saat tertutup, emas saat terbuka
  - Item   : bintang 4 tepi biru muda
  - Portal : oval vertikal DUA ARAH -- setiap PASANGAN portal (dua sel yang
             saling terhubung) diwarnai sama, dan beda pasangan beda warna
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # tidak perlu display, langsung simpan ke file
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.lines import Line2D
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import ListedColormap

WALL_COLOR = "#1f2430"
FREE_COLOR = "#f4f1ea"
UNKNOWN_COLOR = "#c9c9c9"
PATH_COLOR = "#3c6ef0"
START_COLOR = "#2bb673"
EXIT_CLOSED_COLOR = "#8b5a2b"   # coklat
EXIT_OPEN_COLOR = "#e8b84b"    # emas
ITEM_COLOR = "#7ec8e3"         # biru muda
ITEM_EDGE_COLOR = "#2b6a85"
AGENT_COLOR = "#ff6f3c"

# satu warna per pasang portal (dipakai bergantian lewat index % len(...))
PORTAL_PALETTE = ["#8e44ad", "#16a085", "#e67e22", "#2980b9",
                   "#c0392b", "#27ae60", "#d35400", "#6c5ce7"]


def _star_path(n_points=4, inner_ratio=0.42):
    """Path matplotlib custom: bintang dengan n_points ujung (default 4)."""
    angles = np.linspace(0, 2 * np.pi, n_points * 2, endpoint=False) + np.pi / 2
    radii = np.empty(n_points * 2)
    radii[0::2] = 1.0
    radii[1::2] = inner_ratio
    verts = np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])
    verts = np.vstack([verts, verts[0]])
    codes = [Path.MOVETO] + [Path.LINETO] * (n_points * 2 - 1) + [Path.CLOSEPOLY]
    return Path(verts, codes)


def _oval_path(rx=0.55, ry=1.0, n=28):
    """Path matplotlib custom: oval/elips VERTIKAL (lebih tinggi dari lebar)."""
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    verts = np.column_stack([rx * np.cos(theta), ry * np.sin(theta)])
    verts = np.vstack([verts, verts[0]])
    codes = [Path.MOVETO] + [Path.LINETO] * (n - 1) + [Path.CLOSEPOLY]
    return Path(verts, codes)


def _door_path(width=0.62, height=1.35, n_arc=14):
    """Path matplotlib custom: persegi panjang vertikal + atap melengkung, seperti pintu."""
    hw = width / 2
    straight_h = height - hw
    bottom_y = -height / 2
    arc_center_y = bottom_y + straight_h
    pts = [(-hw, bottom_y), (-hw, arc_center_y)]
    for i in range(n_arc + 1):
        t = np.pi - (np.pi * i / n_arc)
        pts.append((hw * np.cos(t), arc_center_y + hw * np.sin(t)))
    pts.append((hw, bottom_y))
    pts.append((-hw, bottom_y))
    verts = np.array(pts)
    codes = [Path.MOVETO] + [Path.LINETO] * (len(verts) - 2) + [Path.CLOSEPOLY]
    return Path(verts, codes)


STAR4 = _star_path(4)
OVAL_V = _oval_path()
DOOR = _door_path()


def portal_color(pair_id):
    return PORTAL_PALETTE[pair_id % len(PORTAL_PALETTE)]


def _grid_to_array(grid):
    return [[0 if cell == "wall" else 1 for cell in row] for row in grid]


def _draw_base(ax, grid, title):
    arr = _grid_to_array(grid)
    cmap = ListedColormap([WALL_COLOR, FREE_COLOR])
    ax.imshow(arr, cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])


def _scatter_items(ax, cells, zorder=3):
    if not cells:
        return
    iy, ix = zip(*cells)
    ax.scatter(ix, iy, marker=STAR4, facecolor=ITEM_COLOR, edgecolor=ITEM_EDGE_COLOR,
               linewidths=0.9, s=190, zorder=zorder)


def _scatter_portals(ax, portal_dict, zorder=3):
    """portal_dict: {sel: pair_id}. Tiap pasangan (sama pair_id) digambar warna sama."""
    by_pair = {}
    for cell, pid in portal_dict.items():
        by_pair.setdefault(pid, []).append(cell)
    for pid, cells in by_pair.items():
        cy, cx = zip(*cells)
        ax.scatter(cx, cy, marker=OVAL_V, facecolor=portal_color(pid),
                   edgecolor="white", linewidths=0.7, s=190, zorder=zorder)


def plot_final_result(env, agent, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 6.4))

    # ---- panel kiri: ground truth + jejak lengkap ----
    _draw_base(ax1, env.grid, "Peta Sebenarnya (Ground Truth) + Jejak Agent")
    xs = [c for _, c in agent.trajectory]
    ys = [r for r, _ in agent.trajectory]
    ax1.plot(xs, ys, color=PATH_COLOR, linewidth=1.6, alpha=0.85, zorder=2)

    sr, sc = env.start
    er, ec = env.exit_pos
    ax1.scatter([sc], [sr], color=START_COLOR, s=170, marker="s", zorder=3)
    exit_color = EXIT_OPEN_COLOR if env.exit_open else EXIT_CLOSED_COLOR
    ax1.scatter([ec], [er], marker=DOOR, facecolor=exit_color, edgecolor="none", s=260, zorder=3)

    _scatter_items(ax1, env.original_items)
    portals_gt = {cell: pid for cell, pid in env.portal_pair_id.items()}
    _scatter_portals(ax1, portals_gt)

    far, fac = agent.pos
    ax1.scatter([fac], [far], color=AGENT_COLOR, s=100, marker="o", zorder=4)

    # ---- panel kanan: peta yang berhasil DIKETAHUI agent ----
    ax2.set_title("Peta yang Diketahui Agent\n(Partially Observable)", fontsize=12, fontweight="bold")
    rows, cols = env.rows, env.cols
    arr = [[2] * cols for _ in range(rows)]  # 2 = unknown (abu-abu)
    for (r, c), t in agent.known_map.items():
        arr[r][c] = 0 if t == "wall" else 1
    cmap2 = ListedColormap([WALL_COLOR, FREE_COLOR, UNKNOWN_COLOR])
    ax2.imshow(arr, cmap=cmap2, vmin=0, vmax=2, interpolation="nearest")
    ax2.plot(xs, ys, color=PATH_COLOR, linewidth=1.6, alpha=0.85, zorder=2)
    ax2.scatter([sc], [sr], color=START_COLOR, s=170, marker="s", zorder=3)
    if agent.known_exit:
        ax2.scatter([ec], [er], marker=DOOR, facecolor=exit_color, edgecolor="none", s=260, zorder=3)
    _scatter_items(ax2, agent.known_items)
    _scatter_portals(ax2, agent.known_portals)
    ax2.scatter([fac], [far], color=AGENT_COLOR, s=100, marker="o", zorder=4)
    ax2.set_xticks([])
    ax2.set_yticks([])

    legend_handles = [
        Line2D([0], [0], marker="s", linestyle="none", markerfacecolor=START_COLOR,
               markeredgecolor="none", markersize=11, label="Start"),
        Line2D([0], [0], marker=DOOR, linestyle="none", markerfacecolor=EXIT_OPEN_COLOR,
               markeredgecolor="none", markersize=15, label="Exit (terbuka)"),
        Line2D([0], [0], marker=DOOR, linestyle="none", markerfacecolor=EXIT_CLOSED_COLOR,
               markeredgecolor="none", markersize=15, label="Exit (tertutup)"),
        Line2D([0], [0], marker=STAR4, linestyle="none", markerfacecolor=ITEM_COLOR,
               markeredgecolor=ITEM_EDGE_COLOR, markersize=13, label="Item"),
        Line2D([0], [0], marker="o", linestyle="none", markerfacecolor=AGENT_COLOR,
               markeredgecolor="none", markersize=11, label="Posisi akhir agent"),
        Line2D([0], [0], marker="s", linestyle="none", markerfacecolor=UNKNOWN_COLOR,
               markeredgecolor="none", markersize=11, label="Belum tersensor"),
    ]
    for pid in range(len(env.portal_pairs)):
        legend_handles.append(
            Line2D([0], [0], marker=OVAL_V, linestyle="none", markerfacecolor=portal_color(pid),
                   markeredgecolor="white", markersize=13, label=f"Portal pasangan {pid + 1} (2 arah)")
        )

    fig.legend(handles=legend_handles, loc="lower center", ncol=4, fontsize=9,
               bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def make_animation(env, agent, save_path, fps=6):
    rows, cols = env.rows, env.cols
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    cmap = ListedColormap([WALL_COLOR, FREE_COLOR, UNKNOWN_COLOR])

    def frame_array(snap):
        arr = [[2] * cols for _ in range(rows)]
        for (r, c), t in snap["known_map"].items():
            arr[r][c] = 0 if t == "wall" else 1
        return arr

    im = ax.imshow(frame_array(agent.history[0]), cmap=cmap, vmin=0, vmax=2,
                    interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    sr, sc = env.start
    er, ec = env.exit_pos
    ax.plot([sc], [sr], "s", color=START_COLOR, markersize=10, zorder=3)
    agent_dot, = ax.plot([], [], "o", color=AGENT_COLOR, markersize=9, zorder=5)
    exit_dot, = ax.plot([], [], linestyle="none", marker=DOOR, markersize=16,
                         markerfacecolor=EXIT_CLOSED_COLOR, markeredgecolor="none", zorder=4)
    items_dots, = ax.plot([], [], linestyle="none", marker=STAR4, markersize=13,
                           markerfacecolor=ITEM_COLOR, markeredgecolor=ITEM_EDGE_COLOR,
                           zorder=4)
    # satu Line2D per pasang portal yg MUNGKIN muncul, supaya warnanya konsisten per pasang
    portal_artists = []
    for pid in range(len(env.portal_pairs)):
        artist, = ax.plot([], [], linestyle="none", marker=OVAL_V, markersize=12,
                           markerfacecolor=portal_color(pid), markeredgecolor="white",
                           markeredgewidth=0.6, zorder=4)
        portal_artists.append(artist)
    title = ax.set_title("")

    def update(i):
        snap = agent.history[i]
        im.set_data(frame_array(snap))
        ar, ac = snap["pos"]
        agent_dot.set_data([ac], [ar])

        if snap["known_exit"]:
            exit_dot.set_data([ec], [er])
            all_done = len(snap["collected_items"]) == env.total_items
            exit_dot.set_markerfacecolor(EXIT_OPEN_COLOR if all_done else EXIT_CLOSED_COLOR)

        remaining = snap["known_items"] - snap["collected_items"]
        if remaining:
            iy, ix = zip(*remaining)
            items_dots.set_data(list(ix), list(iy))
        else:
            items_dots.set_data([], [])

        by_pair = {}
        for cell, pid in snap["known_portals"].items():
            by_pair.setdefault(pid, []).append(cell)
        for pid, artist in enumerate(portal_artists):
            cells = by_pair.get(pid)
            if cells:
                cy, cx = zip(*cells)
                artist.set_data(list(cx), list(cy))
            else:
                artist.set_data([], [])

        title.set_text(f"Langkah {i} | aksi: {snap['action']} | "
                        f"item: {len(snap['collected_items'])}/{env.total_items}")
        return (im, agent_dot, exit_dot, items_dots, title, *portal_artists)

    anim = FuncAnimation(fig, update, frames=len(agent.history), blit=False)
    anim.save(save_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
