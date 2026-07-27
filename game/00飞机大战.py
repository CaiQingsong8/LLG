import random
import time
import tkinter as tk


WIDTH = 480
HEIGHT = 640
PLAYER_SPEED = 8
BULLET_SPEED = 12
ENEMY_SPEED_MIN = 2
ENEMY_SPEED_MAX = 5
SPAWN_INTERVAL_MS = 600
FRAME_MS = 16


class Game:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("飞机大战")
        self.canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg="#0b1b2b")
        self.canvas.pack()

        self.score = 0
        self.running = True

        self.score_text = self.canvas.create_text(
            10, 10, anchor="nw", fill="white", font=("Arial", 12), text="Score: 0"
        )

        self.player = self.canvas.create_polygon(
            WIDTH // 2,
            HEIGHT - 50,
            WIDTH // 2 - 15,
            HEIGHT - 20,
            WIDTH // 2 + 15,
            HEIGHT - 20,
            fill="#4fd1c5",
            outline="white",
        )

        # (canvas_id, x, y, x2, y2)
        self.bullets: list[tuple[int, int, int, int, int]] = []
        # (canvas_id, x, y, x2, y2, speed)
        self.enemies: list[tuple[int, int, int, int, int, int]] = []

        self.keys = {"Left": False, "Right": False, "space": False}
        self.last_shot = 0.0
        self.canvas.bind("<KeyPress>", self.on_key_press)
        self.canvas.bind("<KeyRelease>", self.on_key_release)
        self.canvas.focus_set()

        self.root.after(SPAWN_INTERVAL_MS, self.spawn_enemy)
        self.root.after(FRAME_MS, self.update)

    def on_key_press(self, event: tk.Event) -> None:
        if event.keysym in self.keys:
            self.keys[event.keysym] = True

    def on_key_release(self, event: tk.Event) -> None:
        if event.keysym in self.keys:
            self.keys[event.keysym] = False

    def spawn_enemy(self) -> None:
        if not self.running:
            return
        x = random.randint(20, WIDTH - 20)
        size = random.randint(16, 26)
        bx1, by1, bx2, by2 = x - size, -size * 2, x + size, 0
        cid = self.canvas.create_oval(bx1, by1, bx2, by2, fill="#f56565", outline="white")
        speed = random.randint(ENEMY_SPEED_MIN, ENEMY_SPEED_MAX)
        self.enemies.append((cid, bx1, by1, bx2, by2, speed))
        self.root.after(SPAWN_INTERVAL_MS, self.spawn_enemy)

    def shoot(self) -> None:
        px1, py1, px2, py2 = self.canvas.bbox(self.player)
        cx = (px1 + px2) // 2
        bx1, by1, bx2, by2 = cx - 2, py1 - 10, cx + 2, py1
        cid = self.canvas.create_rectangle(bx1, by1, bx2, by2, fill="yellow")
        self.bullets.append((cid, bx1, by1, bx2, by2))

    def update_player(self) -> None:
        dx = 0
        if self.keys["Left"]:
            dx -= PLAYER_SPEED
        if self.keys["Right"]:
            dx += PLAYER_SPEED
        if dx != 0:
            self.canvas.move(self.player, dx, 0)
            x1, _, x2, _ = self.canvas.bbox(self.player)
            if x1 < 0:
                self.canvas.move(self.player, -x1, 0)
            elif x2 > WIDTH:
                self.canvas.move(self.player, WIDTH - x2, 0)

        if self.keys["space"]:
            now = time.time()
            if now - self.last_shot >= 0.2:
                self.shoot()
                self.last_shot = now

    def update_bullets(self) -> None:
        active = []
        for cid, bx1, by1, bx2, by2 in self.bullets:
            by1 -= BULLET_SPEED
            by2 -= BULLET_SPEED
            if by2 < 0:
                self.canvas.delete(cid)
            else:
                self.canvas.move(cid, 0, -BULLET_SPEED)
                active.append((cid, bx1, by1, bx2, by2))
        self.bullets = active

    def update_enemies(self) -> None:
        active = []
        for cid, ex1, ey1, ex2, ey2, speed in self.enemies:
            ey1 += speed
            ey2 += speed
            if ey1 > HEIGHT:
                self.canvas.delete(cid)
            else:
                self.canvas.move(cid, 0, speed)
                active.append((cid, ex1, ey1, ex2, ey2, speed))
        self.enemies = active

    @staticmethod
    def _overlap(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2) -> bool:
        return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1

    def check_collisions(self) -> None:
        px1, py1, px2, py2 = self.canvas.bbox(self.player)
        if not px1:
            return

        # player vs enemies
        for _, ex1, ey1, ex2, ey2, _ in self.enemies:
            if self._overlap(px1, py1, px2, py2, ex1, ey1, ex2, ey2):
                self.game_over()
                return

        # bullets vs enemies
        hit_bullets: set[int] = set()
        hit_enemies: set[int] = set()
        for bcid, bx1, by1, bx2, by2 in self.bullets:
            if bcid in hit_bullets:
                continue
            for ecid, ex1, ey1, ex2, ey2, _ in self.enemies:
                if ecid in hit_enemies:
                    continue
                if self._overlap(bx1, by1, bx2, by2, ex1, ey1, ex2, ey2):
                    hit_bullets.add(bcid)
                    hit_enemies.add(ecid)
                    break

        for cid in hit_bullets:
            self.canvas.delete(cid)
        for cid in hit_enemies:
            self.canvas.delete(cid)
        self.bullets = [b for b in self.bullets if b[0] not in hit_bullets]
        self.enemies = [e for e in self.enemies if e[0] not in hit_enemies]

        self.score += len(hit_enemies) * 10
        if hit_enemies:
            self.canvas.itemconfig(self.score_text, text=f"Score: {self.score}")

    def game_over(self) -> None:
        self.running = False
        self.canvas.create_text(
            WIDTH // 2,
            HEIGHT // 2,
            fill="white",
            font=("Arial", 24, "bold"),
            text="GAME OVER",
        )

    def update(self) -> None:
        if not self.running:
            return
        self.update_player()
        self.update_bullets()
        self.update_enemies()
        self.check_collisions()
        self.root.after(FRAME_MS, self.update)


if __name__ == "__main__":
    root = tk.Tk()
    Game(root)
    root.mainloop()
