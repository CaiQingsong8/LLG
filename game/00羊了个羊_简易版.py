import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tkinter as tk
import wave

TITLE = "00羊了个羊_简易版"
PADDING = 12
CELL = 60
LAYER_SHIFT = 6
TRAY_SIZE = 7
BG_TOP = (186, 224, 255)
BG_BOTTOM = (120, 188, 120)
TYPE_LABELS = ["草", "羊", "铃", "奶", "云", "星", "果", "叶", "露"]
TYPE_COLORS = [
    "#F1C40F",
    "#ECF0F1",
    "#E67E22",
    "#3498DB",
    "#9B59B6",
    "#2ECC71",
    "#E74C3C",
    "#1ABC9C",
    "#F39C12",
]
LAYERS = [
    {"rows": 7, "cols": 9, "offset": (0, 0)},
    {"rows": 6, "cols": 7, "offset": (1, 1)},
    {"rows": 3, "cols": 7, "offset": (1, 2)},
]


class SheepMatchGame:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.tiles: list[dict[str, int]] = []
        self.tray: list[int] = []
        self.score = 0
        self.running = True
        self.hint_tile: dict[str, int] | None = None
        self.music_process: subprocess.Popen | None = None
        self.music_after = None
        self.music_duration = 4.0
        self.music_path = os.path.join(os.path.dirname(__file__), "sheep_bgm.wav")

        top = tk.Frame(root, padx=PADDING, pady=PADDING)
        top.pack(fill="x")
        self.info_var = tk.StringVar(value="剩余: 0 | 托盘: 0 | 得分: 0")
        tk.Label(top, text=self.info_var, font=("Helvetica", 14)).pack(side="left")
        tk.Button(top, text="智能提示", command=self.smart_pick).pack(side="right")
        tk.Button(top, text="重开", command=self.reset).pack(side="right", padx=(0, 8))

        self.base_cols, self.base_rows = self.calc_base_grid()
        width = self.base_cols * CELL + PADDING * 2 + LAYER_SHIFT * 3
        height = self.base_rows * CELL + 120
        self.canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0)
        self.canvas.pack(padx=PADDING, pady=(0, PADDING))
        self.canvas.bind("<Button-1>", self.on_click)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.reset()

    def calc_base_grid(self) -> tuple[int, int]:
        max_c = 0
        max_r = 0
        for layer in LAYERS:
            oc, orow = layer["offset"]
            max_c = max(max_c, oc + layer["cols"])
            max_r = max(max_r, orow + layer["rows"])
        return max_c, max_r

    def reset(self) -> None:
        self.score = 0
        self.tray = []
        self.hint_tile = None
        self.running = True
        self.tiles = self.build_tiles()
        self.ensure_music()
        self.start_music()
        self.update_info()
        self.draw()

    def build_tiles(self) -> list[dict[str, int]]:
        positions = []
        for layer_idx, layer in enumerate(LAYERS):
            oc, orow = layer["offset"]
            for r in range(layer["rows"]):
                for c in range(layer["cols"]):
                    positions.append({"gx": c + oc, "gy": r + orow, "layer": layer_idx, "type": -1})
        random.shuffle(positions)
        tile_count = len(positions)
        type_count = len(TYPE_LABELS)
        pool = []
        for i in range(tile_count // 3):
            pool.extend([i % type_count] * 3)
        random.shuffle(pool)
        for idx, tile in enumerate(positions):
            tile["type"] = pool[idx]
        return positions

    def update_info(self) -> None:
        self.info_var.set(
            f"剩余: {len(self.tiles)} | 托盘: {len(self.tray)} | 得分: {self.score}"
        )

    def on_click(self, event: tk.Event) -> None:
        if not self.running:
            return
        tile = self.find_tile_at(event.x, event.y)
        if tile:
            self.pick_tile(tile)

    def find_tile_at(self, x: int, y: int) -> dict[str, int] | None:
        for tile in sorted(self.tiles, key=lambda t: t["layer"], reverse=True):
            if not self.is_top(tile):
                continue
            x0, y0, x1, y1 = self.tile_rect(tile)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return tile
        return None

    def is_top(self, tile: dict[str, int]) -> bool:
        gx, gy, layer = tile["gx"], tile["gy"], tile["layer"]
        for other in self.tiles:
            if other["gx"] == gx and other["gy"] == gy and other["layer"] > layer:
                return False
        return True

    def pick_tile(self, tile: dict[str, int]) -> None:
        self.tiles.remove(tile)
        self.tray.append(tile["type"])
        self.hint_tile = None
        self.clear_triplets()
        self.update_info()
        if len(self.tray) > TRAY_SIZE:
            self.game_over(False)
            return
        if not self.tiles:
            self.game_over(True)
            return
        self.draw()

    def clear_triplets(self) -> None:
        changed = True
        while changed:
            changed = False
            for t in set(self.tray):
                idxs = [i for i, v in enumerate(self.tray) if v == t]
                if len(idxs) >= 3:
                    for i in reversed(idxs[:3]):
                        self.tray.pop(i)
                    self.score += 10
                    changed = True
                    break

    def smart_pick(self) -> None:
        if not self.running:
            return
        counts = {t: self.tray.count(t) for t in set(self.tray)}
        candidates = [t for t in self.tiles if self.is_top(t)]
        if not candidates:
            return
        candidates.sort(key=lambda t: counts.get(t["type"], 0), reverse=True)
        choice = candidates[0]
        self.hint_tile = choice
        self.pick_tile(choice)

    def game_over(self, win: bool) -> None:
        self.running = False
        self.update_info()
        self.draw()
        msg = "你赢了\n点击重开" if win else "托盘满了\n点击重开"
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.create_text(
            w // 2,
            h // 2,
            text=msg,
            fill="#2C3E50",
            font=("Helvetica", 20, "bold"),
            justify="center",
        )

    def tile_rect(self, tile: dict[str, int]) -> tuple[int, int, int, int]:
        x0 = PADDING + tile["gx"] * CELL + tile["layer"] * LAYER_SHIFT
        y0 = PADDING + tile["gy"] * CELL - tile["layer"] * LAYER_SHIFT
        x1 = x0 + CELL - 6
        y1 = y0 + CELL - 6
        return x0, y0, x1, y1

    def draw(self) -> None:
        self.canvas.delete("all")
        self.draw_background()
        for tile in sorted(self.tiles, key=lambda t: t["layer"]):
            x0, y0, x1, y1 = self.tile_rect(tile)
            self.canvas.create_rectangle(x0 + 4, y0 + 6, x1 + 4, y1 + 6, fill="#7F8C8D", outline="")
            fill = TYPE_COLORS[tile["type"]]
            outline = "#2C3E50" if self.is_top(tile) else "#95A5A6"
            width = 3 if tile is self.hint_tile else 2
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=width)
            self.canvas.create_text(
                (x0 + x1) / 2,
                (y0 + y1) / 2,
                text=TYPE_LABELS[tile["type"]],
                fill="#2C3E50",
                font=("Helvetica", 16, "bold"),
            )
        self.draw_tray()

    def draw_background(self) -> None:
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        for i in range(h):
            t = i / max(1, h - 1)
            color = self.mix_color(BG_TOP, BG_BOTTOM, t)
            self.canvas.create_line(0, i, w, i, fill=color)
        hill_y = PADDING + self.base_rows * CELL - 30
        self.canvas.create_oval(-80, hill_y - 120, 200, hill_y + 120, fill="#6FCF97", outline="")
        self.canvas.create_oval(120, hill_y - 140, 420, hill_y + 140, fill="#56CC84", outline="")
        self.canvas.create_oval(340, hill_y - 110, 640, hill_y + 110, fill="#4CAF6F", outline="")

    def draw_tray(self) -> None:
        start_x = PADDING
        start_y = PADDING + self.base_rows * CELL + 20
        slot_w = CELL - 6
        slot_h = CELL - 16
        self.canvas.create_rectangle(
            start_x - 6,
            start_y - 10,
            start_x + TRAY_SIZE * CELL - 6,
            start_y + slot_h + 10,
            fill="#F8F9FA",
            outline="#95A5A6",
        )
        for i in range(TRAY_SIZE):
            x0 = start_x + i * CELL
            y0 = start_y
            x1 = x0 + slot_w
            y1 = y0 + slot_h
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#7F8C8D")
            if i < len(self.tray):
                t = self.tray[i]
                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill=TYPE_COLORS[t], outline="")
                self.canvas.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=TYPE_LABELS[t],
                    fill="#2C3E50",
                    font=("Helvetica", 14, "bold"),
                )

    @staticmethod
    def mix_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
        r = int(a[0] + (b[0] - a[0]) * t)
        g = int(a[1] + (b[1] - a[1]) * t)
        bl = int(a[2] + (b[2] - a[2]) * t)
        return f"#{r:02x}{g:02x}{bl:02x}"

    def ensure_music(self) -> None:
        if os.path.exists(self.music_path):
            return
        sample_rate = 44100
        duration = self.music_duration
        notes = [392.0, 440.0, 523.25, 659.25, 523.25, 440.0, 392.0, 349.23]
        frames = int(sample_rate * duration)
        with wave.open(self.music_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            for i in range(frames):
                t = i / sample_rate
                idx = int(t * 2) % len(notes)
                freq = notes[idx]
                beat = 0.5 + 0.5 * math.sin(2 * math.pi * 2 * t)
                amp = 0.35 * beat
                value = amp * (
                    math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * freq * 2 * t)
                )
                sample = max(-1.0, min(1.0, value))
                wf.writeframes(struct.pack("<h", int(sample * 32767)))

    def start_music(self) -> None:
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(self.music_path, winsound.SND_ASYNC | winsound.SND_LOOP)
            except Exception:
                pass
            return
        if self.music_process and self.music_process.poll() is None:
            return
        player = shutil.which("afplay") or shutil.which("aplay")
        if not player:
            return
        try:
            self.music_process = subprocess.Popen(
                [player, self.music_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            self.music_process = None
            return
        if self.music_after:
            self.root.after_cancel(self.music_after)
        self.music_after = self.root.after(int(self.music_duration * 1000), self.start_music)

    def stop_music(self) -> None:
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_ASYNC)
            except Exception:
                pass
            return
        if self.music_after:
            self.root.after_cancel(self.music_after)
            self.music_after = None
        if self.music_process and self.music_process.poll() is None:
            self.music_process.terminate()
        self.music_process = None

    def on_close(self) -> None:
        self.stop_music()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    SheepMatchGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()
