import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tkinter as tk
import wave

TITLE = "00贪吃蛇"
CELL = 20
GRID = 25
PADDING = 10
SPEED_MS = 240
BG = "#1B1E2B"
SNAKE = "#2ECC71"
HEAD = "#27AE60"
FOOD = "#E74C3C"
GRID_LINE = "#2C3E50"
STAR_COUNT = 45
PARTICLE_COUNT = 14


class SnakeGame:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.running = True
        self.score = 0
        self.direction = (1, 0)
        self.pending_dir = self.direction
        self.snake: list[tuple[int, int]] = []
        self.food: tuple[int, int] | None = None
        self.timer = None
        self.stars: list[tuple[float, float, float, int]] = []
        self.particles: list[tuple[float, float, float, float, int, str]] = []
        self.flash = 0
        self.music_process: subprocess.Popen | None = None
        self.music_after = None
        self.music_duration = 4.0
        self.music_path = os.path.join(os.path.dirname(__file__), "snake_bgm.wav")

        top = tk.Frame(root, padx=PADDING, pady=PADDING)
        top.pack(fill="x")
        self.score_var = tk.StringVar(value="得分: 0")
        tk.Label(top, text=self.score_var, font=("Helvetica", 14)).pack(side="left")
        tk.Button(top, text="重开", command=self.reset).pack(side="right")

        size = GRID * CELL
        self.canvas = tk.Canvas(root, width=size, height=size, bg=BG, highlightthickness=0)
        self.canvas.pack(padx=PADDING, pady=(0, PADDING))

        root.bind("<Up>", lambda _e: self.turn(0, -1))
        root.bind("<Down>", lambda _e: self.turn(0, 1))
        root.bind("<Left>", lambda _e: self.turn(-1, 0))
        root.bind("<Right>", lambda _e: self.turn(1, 0))
        root.bind("<w>", lambda _e: self.turn(0, -1))
        root.bind("<s>", lambda _e: self.turn(0, 1))
        root.bind("<a>", lambda _e: self.turn(-1, 0))
        root.bind("<d>", lambda _e: self.turn(1, 0))

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.reset()

    def reset(self) -> None:
        if self.timer:
            self.root.after_cancel(self.timer)
        self.running = True
        self.score = 0
        self.score_var.set("得分: 0")
        self.direction = (1, 0)
        self.pending_dir = self.direction
        mid = GRID // 2
        self.snake = [(mid, mid), (mid - 1, mid), (mid - 2, mid)]
        self.stars = self.create_stars()
        self.particles = []
        self.flash = 0
        self.ensure_music()
        self.start_music()
        self.place_food()
        self.draw()
        self.tick()

    def place_food(self) -> None:
        occupied = set(self.snake)
        while True:
            pos = (random.randrange(GRID), random.randrange(GRID))
            if pos not in occupied:
                self.food = pos
                return

    def turn(self, dx: int, dy: int) -> None:
        if not self.running:
            return
        cur_dx, cur_dy = self.direction
        if (dx, dy) == (-cur_dx, -cur_dy):
            return
        self.pending_dir = (dx, dy)

    def tick(self) -> None:
        if not self.running:
            return
        self.direction = self.pending_dir
        dx, dy = self.direction
        head_x, head_y = self.snake[0]
        nx = head_x + dx
        ny = head_y + dy
        if not (0 <= nx < GRID and 0 <= ny < GRID):
            self.game_over()
            return
        new_head = (nx, ny)
        if new_head in self.snake:
            self.game_over()
            return
        self.snake.insert(0, new_head)
        if self.food and new_head == self.food:
            self.score += 10
            self.score_var.set(f"得分: {self.score}")
            self.flash = 6
            self.spawn_particles(new_head, FOOD)
            self.place_food()
        else:
            self.snake.pop()
        self.update_effects()
        self.draw()
        self.timer = self.root.after(SPEED_MS, self.tick)

    def game_over(self) -> None:
        self.running = False
        self.spawn_particles(self.snake[0], "#F39C12", burst=26, speed=3.5)
        self.draw()
        self.canvas.create_text(
            GRID * CELL // 2,
            GRID * CELL // 2,
            text="游戏结束\n点击重开",
            fill="#ECF0F1",
            font=("Helvetica", 18, "bold"),
            justify="center",
        )

    def draw(self) -> None:
        self.canvas.delete("all")
        self.draw_background()
        for x, y, _speed, size in self.stars:
            self.canvas.create_oval(x, y, x + size, y + size, fill="#4A5568", outline="")
        if self.food:
            fx, fy = self.food
            self.draw_cell(fx, fy, FOOD)
        for idx, (x, y) in enumerate(self.snake):
            color = HEAD if idx == 0 else SNAKE
            self.draw_cell(x, y, color)
        for x, y, _vx, _vy, life, color in self.particles:
            radius = max(1.0, life * 0.12)
            self.canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius, fill=color, outline=""
            )
        if self.flash > 0:
            hx, hy = self.snake[0]
            cx = hx * CELL + CELL / 2
            cy = hy * CELL + CELL / 2
            radius = (7 - self.flash) * 6
            self.canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius, outline="#F1C40F", width=2
            )
        for i in range(GRID + 1):
            p = i * CELL
            self.canvas.create_line(p, 0, p, GRID * CELL, fill=GRID_LINE)
            self.canvas.create_line(0, p, GRID * CELL, p, fill=GRID_LINE)

    def draw_cell(self, x: int, y: int, color: str) -> None:
        x0 = x * CELL
        y0 = y * CELL
        x1 = x0 + CELL
        y1 = y0 + CELL
        self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill=color, outline="")

    def draw_background(self) -> None:
        start = (14, 21, 39)
        end = (34, 52, 74)
        for i in range(GRID):
            t = i / max(1, GRID - 1)
            color = self.mix_color(start, end, t)
            y0 = i * CELL
            y1 = y0 + CELL
            self.canvas.create_rectangle(0, y0, GRID * CELL, y1, fill=color, outline="")

    @staticmethod
    def mix_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
        r = int(a[0] + (b[0] - a[0]) * t)
        g = int(a[1] + (b[1] - a[1]) * t)
        bl = int(a[2] + (b[2] - a[2]) * t)
        return f"#{r:02x}{g:02x}{bl:02x}"

    def create_stars(self) -> list[tuple[float, float, float, int]]:
        stars = []
        for _ in range(STAR_COUNT):
            x = random.uniform(0, GRID * CELL)
            y = random.uniform(0, GRID * CELL)
            speed = random.uniform(0.2, 0.6)
            size = random.choice([1, 2])
            stars.append((x, y, speed, size))
        return stars

    def update_effects(self) -> None:
        new_stars = []
        for x, y, speed, size in self.stars:
            y += speed
            if y > GRID * CELL:
                y = 0
                x = random.uniform(0, GRID * CELL)
            new_stars.append((x, y, speed, size))
        self.stars = new_stars
        updated = []
        for x, y, vx, vy, life, color in self.particles:
            if life <= 0:
                continue
            x += vx
            y += vy
            vy += 0.12
            life -= 1
            updated.append((x, y, vx, vy, life, color))
        self.particles = updated
        if self.flash > 0:
            self.flash -= 1

    def spawn_particles(
        self,
        cell: tuple[int, int],
        color: str,
        burst: int | None = None,
        speed: float = 2.4,
    ) -> None:
        cx = cell[0] * CELL + CELL / 2
        cy = cell[1] * CELL + CELL / 2
        count = burst or PARTICLE_COUNT
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            vx = math.cos(angle) * random.uniform(0.6, speed)
            vy = math.sin(angle) * random.uniform(0.6, speed)
            life = random.randint(10, 18)
            self.particles.append((cx, cy, vx, vy, life, color))

    def ensure_music(self) -> None:
        if os.path.exists(self.music_path):
            return
        sample_rate = 44100
        duration = self.music_duration
        notes = [392.0, 440.0, 523.25, 659.25, 784.0, 659.25, 523.25, 440.0]
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
    SnakeGame(root)
    root.mainloop()


if __name__ == "__main__":
    main()
