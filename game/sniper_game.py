import math
import random
import time
import tkinter as tk

TITLE = "Sniper Hunt"
WIDTH = 960
HEIGHT = 540
FPS = 30

BG = "#10131a"
PANEL = "#1c2230"
TEXT = "#e7ecf4"
HINT = "#8ea2c0"

BASE_TARGETS = 12
BASE_ROBOTS = 2
BASE_TIME = 14.0

MIN_RADIUS = 10
MAX_RADIUS = 20
PADDING = 18


class SniperGame:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg=BG, highlightthickness=0)
        self.canvas.pack()

        self.level = 1
        self.items: list[dict] = []
        self.deadline = 0.0
        self.found = 0
        self.total_robots = 0
        self.game_over = False

        self.root.bind("<Button-1>", self.on_click)
        self.root.bind("<KeyPress-r>", self.on_restart)
        self.root.bind("<KeyPress-R>", self.on_restart)

    def on_restart(self, _event: tk.Event) -> None:
        if self.game_over:
            self.level = 1
            self.start_level()

    def run(self) -> None:
        self.start_level()
        self.tick()
        self.root.mainloop()

    def start_level(self) -> None:
        self.items = []
        self.found = 0
        self.game_over = False
        self.total_robots = BASE_ROBOTS + max(0, self.level - 1)
        target_count = BASE_TARGETS + (self.level - 1) * 4
        time_limit = max(6.0, BASE_TIME - (self.level - 1) * 1.5)
        self.deadline = time.perf_counter() + time_limit
        self.spawn_items(target_count, self.total_robots)

    def spawn_items(self, target_count: int, robot_count: int) -> None:
        robots_left = robot_count
        attempts = 0
        while len(self.items) < target_count and attempts < target_count * 200:
            attempts += 1
            radius = random.uniform(MIN_RADIUS, MAX_RADIUS)
            x = random.uniform(PADDING + radius, WIDTH - PADDING - radius)
            y = random.uniform(80 + radius, HEIGHT - PADDING - radius)
            if self.overlaps(x, y, radius):
                continue
            is_robot = False
            if robots_left > 0:
                is_robot = True
                robots_left -= 1
            self.items.append(
                {
                    "x": x,
                    "y": y,
                    "r": radius,
                    "robot": is_robot,
                    "alive": True,
                }
            )
        random.shuffle(self.items)

    def overlaps(self, x: float, y: float, r: float) -> bool:
        for item in self.items:
            if math.hypot(item["x"] - x, item["y"] - y) < item["r"] + r + 6:
                return True
        return False

    def on_click(self, event: tk.Event) -> None:
        if self.game_over:
            return
        hit = self.pick_item(event.x, event.y)
        if not hit:
            self.deadline -= 0.7
            return
        if hit["robot"]:
            hit["alive"] = False
            self.found += 1
            if self.found >= self.total_robots:
                self.level += 1
                self.start_level()
        else:
            self.deadline -= 1.2

    def pick_item(self, x: float, y: float) -> dict | None:
        best = None
        best_d = 1e9
        for item in self.items:
            if not item["alive"]:
                continue
            d = math.hypot(item["x"] - x, item["y"] - y)
            if d <= item["r"] and d < best_d:
                best = item
                best_d = d
        return best

    def tick(self) -> None:
        now = time.perf_counter()
        if not self.game_over and now >= self.deadline:
            self.game_over = True
        self.draw()
        delay = max(1, int(1000 / FPS))
        self.root.after(delay, self.tick)

    def draw(self) -> None:
        self.canvas.delete("all")
        self.draw_panel()
        self.draw_items()
        self.draw_hud()
        if self.game_over:
            self.draw_game_over()

    def draw_panel(self) -> None:
        self.canvas.create_rectangle(0, 0, WIDTH, 70, fill=PANEL, outline="")

    def draw_items(self) -> None:
        disguise_factor = min(0.75, 0.15 + (self.level - 1) * 0.06)
        for item in self.items:
            if not item["alive"]:
                continue
            base = "#2a313f"
            shade = "#2f3748" if random.random() > 0.5 else "#262c39"
            fill = shade if not item["robot"] else base
            x0 = item["x"] - item["r"]
            y0 = item["y"] - item["r"]
            x1 = item["x"] + item["r"]
            y1 = item["y"] + item["r"]
            self.canvas.create_oval(x0, y0, x1, y1, fill=fill, outline="")

            if item["robot"]:
                mark_r = max(2.0, item["r"] * (0.35 - disguise_factor))
                mark = "#7fa3ff"
                self.canvas.create_oval(
                    item["x"] - mark_r,
                    item["y"] - mark_r,
                    item["x"] + mark_r,
                    item["y"] + mark_r,
                    outline=mark,
                    width=2,
                )

    def draw_hud(self) -> None:
        time_left = max(0.0, self.deadline - time.perf_counter())
        self.canvas.create_text(18, 22, anchor="w", fill=TEXT, text=f"Level: {self.level}")
        self.canvas.create_text(18, 48, anchor="w", fill=HINT, text="Click the disguised robots")
        self.canvas.create_text(
            WIDTH / 2,
            22,
            anchor="n",
            fill=TEXT,
            text=f"Robots: {self.found}/{self.total_robots}",
        )
        self.canvas.create_text(
            WIDTH - 18,
            22,
            anchor="e",
            fill=TEXT,
            text=f"Time: {time_left:0.1f}s",
        )

    def draw_game_over(self) -> None:
        self.canvas.create_rectangle(0, 0, WIDTH, HEIGHT, fill="#000000", stipple="gray50", outline="")
        self.canvas.create_text(
            WIDTH / 2,
            HEIGHT / 2 - 10,
            fill=TEXT,
            text="Mission Failed",
            font=("Helvetica", 32, "bold"),
        )
        self.canvas.create_text(
            WIDTH / 2,
            HEIGHT / 2 + 32,
            fill=HINT,
            text="Press R to restart",
            font=("Helvetica", 16),
        )


def main() -> None:
    root = tk.Tk()
    game = SniperGame(root)
    game.run()


if __name__ == "__main__":
    main()
