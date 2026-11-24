# Simulasi Maze Escape & Item Collector Agent (BFS)

Implementasi kode untuk project **"Simulasi Maze Escape & Item Collector Agent Berbasis
Algoritma BFS"** (Kelompok 4), sesuai isi PPT (Latar Belakang, Tujuan, P.E.A.S, Sifat
Environment, Problem Formulation), ditambah keputusan pada slide **Pertimbangan**:

| # | Pertimbangan di PPT | Keputusan yang dipakai |
|---|---|---|
| 1 | Fully vs Partially Observable | **Partially Observable** |
| 2 | Single vs Multi-Agent | **Single Agent** |
| 3 | Pure BFS vs BFS + Heuristic | **Pure BFS** (tanpa heuristic) |
| 4 | Perlu elemen puzzle/gimmick atau tidak | **Ada** — gimmick *teleport portal dua arah* di beberapa dead-end (opsional, atur lewat `--portals`, default 2 pasang, `--portals 0` untuk matikan) |

> Catatan: keputusan di atas masih bisa berubah — lihat bagian
> [Jika Keputusan Berubah](#jika-keputusan-berubah-nanti) di bawah untuk titik ubah di
> kode kalau pilihannya nanti berbeda lagi.

## Simbol pada Visualisasi

| Simbol | Arti |
|---|---|
| Kotak hijau | Start |
| Pintu coklat (persegi panjang vertikal + atap melengkung) | Exit (tertutup — masih ada item tersisa) |
| Pintu emas | Exit (terbuka — semua item sudah terkumpul) |
| Bintang 4 tepi biru muda | Item |
| Oval vertikal berwarna | Portal — **dua arah**; dua sel dengan warna yang SAMA = satu pasang yang saling terhubung (beda pasang beda warna) |
| Lingkaran oranye | Posisi akhir agent |
| Abu-abu (panel kanan) | Sel yang belum pernah tersensor |

Di ASCII map (`print_known_map`, dicetak di terminal): `S`=start, `E`=exit diketahui,
`A`=posisi agent, `*`=item diketahui, angka `0`-`9`=sel portal diketahui (menunjukkan
indeks pasangannya — dua sel dengan angka sama saling terhubung), `#`=dinding diketahui,
`.`=jalan diketahui, spasi=belum tersensor.

## Struktur File

```
agent_ai_bfs/
├── maze_env.py      # Environment: grid, generator maze random, portal, parser maze custom, sensor
├── agent.py         # Agent: knowledge base + BFS murni (navigasi & eksplorasi) + efek teleport
├── visualize.py      # Render PNG hasil akhir + animasi GIF proses eksplorasi
├── main.py          # CLI: jalankan simulasi end-to-end
├── contoh_maze.txt  # Contoh format maze custom (opsional)
├── requirements.txt
└── output/          # Hasil visualisasi (dibuat otomatis)
```

## Cara Menjalankan

```bash
pip install -r requirements.txt

python main.py                                   # pengaturan default (10x10, 5 item, 2 portal)
python main.py --rows 12 --cols 12 --items 6 --seed 42 --animate
python main.py --maze-file contoh_maze.txt --animate
python main.py --fully-observable                # bandingkan dgn Fully Observable
python main.py --portals 0                       # matikan gimmick teleport
```

Semua opsi: `python main.py --help`. Output: trace langkah di terminal, peta pengetahuan
agent (ASCII), `output/hasil_akhir.png`, dan (jika `--animate`) `output/simulasi.gif`.

## Batch Banyak Percobaan (mis. 200x) — `batch_run.py`

```bash
python batch_run.py --n 200 --clean               # 200 percobaan, maze beda-beda, paralel
python batch_run.py --n 200 --clean --vary-size   # ukuran maze & jumlah item ikut diacak
python batch_run.py --n 20 --no-gif               # cepat, tanpa GIF
```

Setiap percobaan disimpan di foldernya sendiri (tidak saling menimpa):

```
output/
├── percobaan_001/  hasil_akhir.png, simulasi.gif, maze.txt, log.txt
├── percobaan_002/  ...
└── ringkasan.csv   # rekap: seed, ukuran, status, langkah, teleport, % peta diketahui
```

Keamanan dataset: setiap maze (1) dibangun dari spanning tree sehingga semua sel
terhubung, (2) divalidasi ulang dengan `validate_maze()` (semua item & exit pasti bisa
dicapai dari start), dan (3) dicek unik lewat sidik jari SHA-1, jadi tidak ada maze kembar.
`maze.txt` tiap percobaan bisa diputar ulang: `python main.py --maze-file output/percobaan_001/maze.txt --animate`.

## Bagaimana Tiap Bagian PPT Terpetakan ke Kode

- **P.E.A.S** (slide 4) → `MazeEnvironment` (Environment/Actuators/Sensors) di
  `maze_env.py`, `MazeAgent` (Performance via `agent.log`/`trajectory`) di `agent.py`.
- **Sifat Environment** (slide 5 — deterministik, statis-tapi-dinamis, diskrit, sequential)
  → grid diskrit, `MazeEnvironment.visit()` (item hilang setelah diambil, status exit bisa
  berubah), gerakan selalu pasti tanpa elemen acak.
- **Problem Formulation** (slide 6) → persis jadi `MazeAgent.decide()` (Actions, Transition
  Model) dan goal test di `MazeAgent.step()` (semua item terkumpul + agent di exit).

## Desain Kunci: BFS di Dunia yang Partially Observable

Ini bagian paling penting untuk dipahami, karena **"Partially Observable" + "Pure BFS"**
tidak bisa digabung dengan cara naif (BFS satu kali dari start ke exit mengasumsikan
seluruh peta sudah diketahui — itu baru valid kalau Fully Observable).

Solusinya: agent menjalani loop **Sense → Think → Act** di setiap langkah
(`MazeAgent.step()`), dan BFS murni (`MazeAgent.bfs()`, tanpa heuristic apa pun) dipakai
untuk **dua peran berbeda** tergantung apa yang sudah "dilihat" agent:

1. **Navigasi** — begitu sebuah item (atau exit, setelah semua item terkumpul) sudah
   pernah tersensor, BFS mencari jalur terpendek ke sana lewat sel-sel yang sudah
   *diketahui* bebas.
2. **Eksplorasi** — selama belum ada target yang diketahui, BFS mencari *frontier*
   terdekat (sel bebas yang punya tetangga belum pernah disensor) untuk dikunjungi, agar
   area baru terbuka.

Sensor (`MazeEnvironment.sense`) hanya mengembalikan sel dalam radius tertentu dari posisi
agent (`--vision`, default 1 = tetangga langsung), **persis mencerminkan slide Sensors**
("deteksi dinding", "status item", "posisi & state pintu keluar" — semuanya lokal, bukan
global). Pengambilan item sendiri dianggap efek **aktuator** (bukan sensor jarak jauh) —
begitu agent fisik berada di suatu sel, item di situ otomatis terambil, sesuai Actuators
di P.E.A.S ("pengambilan item otomatis").

Penting: sensing dipanggil **setiap kali posisi agent berubah** (lih. `MazeAgent._arrive`),
bukan cuma sekali di awal setiap langkah. Ini krusial begitu ada portal: kalau agent tiba
di sebuah sel lalu langsung terlempar pergi oleh teleport tanpa sempat "melihat" sekitarnya
dulu, sel itu akan dikira masih punya tetangga belum diketahui selamanya — dan agent bisa
muter-muter ke sana tanpa henti (bug ini sempat terjadi & sudah diperbaiki di versi ini).

Akibat dari keterbatasan sensor (bisa dibuktikan sendiri):
`python main.py --seed 7 --rows 9 --cols 9 --portals 0` butuh **132 langkah**, sedangkan
`--fully-observable` pada seed & maze yang sama cuma **~70-an langkah** — selisihnya adalah
"ongkos" eksplorasi akibat keterbatasan sensor. Dengan portal aktif, ongkos ini biasanya
makin besar lagi (bisa 2-3x lipat) karena teleport kadang membuang agent jauh dari area yang
sedang ia jelajahi, dan ia harus berjalan balik. Ini bisa jadi bahan pembahasan menarik di
laporan/presentasi.

## Gimmick: Teleport Portal Dua Arah

- Dipasang otomatis di sel **dead-end** (ujung buntu, hanya punya 1 tetangga bebas),
  supaya tidak mengganggu jalur utama maze (`maze_env.find_dead_ends` +
  `maze_env.place_portals`).
- **Dua arah**: menginjak salah satu sisi pasangan langsung memindahkan agent ke sisi
  satunya, dan berlaku juga sebaliknya (`MazeEnvironment.portals` menyimpan lookup A→B
  *dan* B→A untuk tiap pasang).
- Setiap **pasangan** punya identitas sendiri (`portal_pair_id`) sehingga bisa digambar
  dengan warna berbeda di visualisasi (oval vertikal, satu warna per pasang).
- **BFS agent tidak diberi tahu soal portal sama sekali** saat merencanakan jalur — ia
  hanya memakai `known_map` (bebas/dinding biasa) seperti biasa. Efek teleport baru
  diterapkan oleh environment SETELAH agent benar-benar melangkah ke sana
  (`MazeAgent.step()` → `env.resolve_teleport()`). Jadi gimmick ini murni "kejutan" di sisi
  environment, dan **tidak mengubah kemurnian algoritma BFS** sama sekali — sesuai
  keputusan #3.
- Di maze custom (`--maze-file`), portal bisa didefinisikan manual pakai pasangan digit
  `1`-`9`: setiap digit yang muncul tepat 2 kali menandai sepasang sel yang saling
  terhubung dua arah.

## Jika Keputusan Berubah Nanti

- **Fully Observable** → sudah tersedia via flag `--fully-observable` (set radius sensor
  sebesar mungkin, jadi satu kali sense langsung membuka seluruh peta).
- **Multi-Agent** → buat beberapa instance `MazeAgent`, jalankan `step()` masing-masing
  bergantian; tinggal putuskan apakah `known_map` dibagi bersama (co-op) atau terpisah
  (v/s), dan tambahkan pengecekan tabrakan antar-agent di `MazeAgent.step()`.
- **BFS + Heuristic** → ganti isi `MazeAgent.bfs()` dari antrean FIFO (`deque`) menjadi
  priority queue (`heapq`) dengan `g(n) + h(n)` (A*); `decide()` tidak perlu diubah sama
  sekali karena hanya memanggil `self.bfs(goal_test)`.
- **Gimmick/puzzle lain** → sudah ada contoh polanya lewat portal (`maze_env.py`); tinggal
  tambah tipe sel baru (mis. `"locked_door"`, `"key"`, trap) dan perluas
  `MazeEnvironment.visit()` dengan logika serupa.
- **Matikan gimmick portal** → `--portals 0`.

## Visualisasi

`output/hasil_akhir.png` berisi dua panel: **peta sebenarnya** (ground truth + seluruh
jejak langkah agent, semua item & portal ditandai) di kiri, dan **peta yang berhasil
diketahui agent** (sel abu-abu = belum pernah tersensor) di kanan — pembuktian visual
langsung bahwa agent berhasil keluar tanpa pernah tahu seluruh labirin sejak awal. Dengan
`--animate`, `output/simulasi.gif` menunjukkan proses itu terjadi bertahap, langkah demi
langkah, termasuk momen-momen teleport (garis lurus memotong peta antara portal masuk &
keluar).
