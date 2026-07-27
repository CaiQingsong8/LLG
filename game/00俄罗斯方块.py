import random
import tkinter as tk

CELL_SIZE = 30
COLS = 10
ROWS = 20
BASE_TICK_MS = 500
MIN_TICK_MS = 100
LEVEL_LINES = 10

SHAPES = {
    "I": [
        [(0, 1), (1, 1), (2, 1), (3, 1)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
    ],
    "O": [
        [(1, 0), (2, 0), (1, 1), (2, 1)],
    ],
    "T": [
        [(1, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (2, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (1, 2)],
        [(1, 0), (0, 1), (1, 1), (1, 2)],
    ],
    "S": [
        [(1, 0), (2, 0), (0, 1), (1, 1)],
        [(1, 0), (1, 1), (2, 1), (2, 2)],
    ],
    "Z": [
        [(0, 0), (1, 0), (1, 1), (2, 1)],
        [(2, 0), (1, 1), (2, 1), (1, 2)],
    ],
    "J": [
        [(0, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (2, 0), (1, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (2, 2)],
        [(1, 0), (1, 1), (0, 2), (1, 2)],
    ],
    "L": [
        [(2, 0), (0, 1), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (1, 2), (2, 2)],
        [(0, 1), (1, 1), (2, 1), (0, 2)],
        [(0, 0), (1, 0), (1, 1), (1, 2)],
    ],
}

COLORS = {
    "I": "#00BCD4",
    "O": "#FFC107",
    "T": "#9C27B0",
    "S": "#4CAF50",
    "Z": "#F44336",
    "J": "#3F51B5",
    "L": "#FF9800",
}


class Tetris:
    def __init__(self, root):
        self.root = root
        self.main_frame = tk.Frame(root)
        self.main_frame.pack()

        self.canvas = tk.Canvas(
            self.main_frame,
            width=COLS * CELL_SIZE,
            height=ROWS * CELL_SIZE,
            bg="#111",
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT)

        self.side_frame = tk.Frame(self.main_frame)
        self.side_frame.pack(side=tk.LEFT, padx=10)

        self.score_var = tk.StringVar(value="Score: 0")
        self.level_var = tk.StringVar(value="Level: 1")
        self.lines_var = tk.StringVar(value="Lines: 0")
        self.pause_var = tk.StringVar(value="")

        tk.Label(self.side_frame, textvariable=self.score_var, font=("Helvetica", 14)).pack(anchor="w")
        tk.Label(self.side_frame, textvariable=self.level_var, font=("Helvetica", 14)).pack(anchor="w")
        tk.Label(self.side_frame, textvariable=self.lines_var, font=("Helvetica", 14)).pack(anchor="w")
        tk.Label(self.side_frame, textvariable=self.pause_var, font=("Helvetica", 12), fg="#888").pack(anchor="w", pady=(2, 8))

        tk.Label(self.side_frame, text="Next", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.next_canvas = tk.Canvas(self.side_frame, width=6 * 20, height=6 * 20, bg="#111", highlightthickness=0)
        self.next_canvas.pack(pady=(2, 10))

        tk.Label(self.side_frame, text="Hold", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.hold_canvas = tk.Canvas(self.side_frame, width=6 * 20, height=6 * 20, bg="#111", highlightthickness=0)
        self.hold_canvas.pack(pady=(2, 10))

        tk.Label(
            self.side_frame,
            text="Keys: \u2190 \u2192 \u2193 move, \u2191 rotate, space drop\nP pause, R restart, C hold",
            font=("Helvetica", 10),
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.score = 0
        self.level = 1
        self.lines = 0
        self.game_over = False
        self.paused = False
        self.current = None
        self.next_piece = None
        self.held_piece = None
        self.hold_used = False
        self.current_pos = (0, 0)
        self.rotation = 0
        self.bag = []

        self.spawn_piece()
        self.bind_keys()
        self.tick()

    def bind_keys(self):
        self.root.bind("<Left>", lambda _e: self.move(-1, 0))
        self.root.bind("<Right>", lambda _e: self.move(1, 0))
        self.root.bind("<Down>", lambda _e: self.move(0, 1))
        self.root.bind("<Up>", lambda _e: self.rotate())
        self.root.bind("<space>", lambda _e: self.hard_drop())
        self.root.bind("<p>", lambda _e: self.toggle_pause())
        self.root.bind("<P>", lambda _e: self.toggle_pause())
        self.root.bind("<r>", lambda _e: self.restart())
        self.root.bind("<R>", lambda _e: self.restart())
        self.root.bind("<c>", lambda _e: self.hold())
        self.root.bind("<C>", lambda _e: self.hold())

    def new_bag(self):
        pieces = list(SHAPES.keys())
        random.shuffle(pieces)
        self.bag.extend(pieces)

    def spawn_piece(self):
        if self.next_piece is None:
            if not self.bag:
                self.new_bag()
            self.next_piece = self.bag.pop(0)
        self.current = self.next_piece
        if not self.bag:
            self.new_bag()
        self.next_piece = self.bag.pop(0)
        self.rotation = 0
        self.current_pos = (3, 0)
        self.hold_used = False
        if self.collides(self.current_pos, self.rotation):
            self.game_over = True
        self.draw_side_panels()

    def blocks(self, pos=None, rotation=None, piece=None):
        piece = piece or self.current
        pos = pos or self.current_pos
        rotation = rotation if rotation is not None else self.rotation
        shape = SHAPES[piece][rotation % len(SHAPES[piece])]
        return [(x + pos[0], y + pos[1]) for x, y in shape]

    def collides(self, pos, rotation):
        for x, y in self.blocks(pos, rotation):
            if x < 0 or x >= COLS or y < 0 or y >= ROWS:
                return True
            if self.grid[y][x] is not None:
                return True
        return False

    def move(self, dx, dy):
        if self.game_over or self.paused:
            return
        new_pos = (self.current_pos[0] + dx, self.current_pos[1] + dy)
        if not self.collides(new_pos, self.rotation):
            self.current_pos = new_pos
            self.draw()
        elif dy == 1:
            self.lock_piece()

    def rotate(self):
        if self.game_over or self.paused:
            return
        new_rot = (self.rotation + 1) % len(SHAPES[self.current])
        if not self.collides(self.current_pos, new_rot):
            self.rotation = new_rot
            self.draw()
            return
        # Simple wall kick
        for dx in (-1, 1, -2, 2):
            test_pos = (self.current_pos[0] + dx, self.current_pos[1])
            if not self.collides(test_pos, new_rot):
                self.current_pos = test_pos
                self.rotation = new_rot
                self.draw()
                return

    def hard_drop(self):
        if self.game_over or self.paused:
            return
        while not self.collides((self.current_pos[0], self.current_pos[1] + 1), self.rotation):
            self.current_pos = (self.current_pos[0], self.current_pos[1] + 1)
        self.lock_piece()

    def hold(self):
        if self.game_over or self.paused or self.hold_used:
            return
        self.hold_used = True
        if self.held_piece is None:
            self.held_piece = self.current
            self.spawn_piece()
        else:
            self.current, self.held_piece = self.held_piece, self.current
            self.rotation = 0
            self.current_pos = (3, 0)
            if self.collides(self.current_pos, self.rotation):
                self.game_over = True
        self.draw()
        self.draw_side_panels()

    def lock_piece(self):
        for x, y in self.blocks():
            if 0 <= y < ROWS and 0 <= x < COLS:
                self.grid[y][x] = COLORS[self.current]
        cleared = self.clear_lines()
        if cleared:
            self.score += [0, 100, 300, 500, 800][cleared]
            self.lines += cleared
            self.level = max(1, self.lines // LEVEL_LINES + 1)
            self.score_var.set(f"Score: {self.score}")
            self.lines_var.set(f"Lines: {self.lines}")
            self.level_var.set(f"Level: {self.level}")
        self.spawn_piece()
        self.draw()

    def clear_lines(self):
        new_grid = [row for row in self.grid if any(cell is None for cell in row)]
        cleared = ROWS - len(new_grid)
        for _ in range(cleared):
            new_grid.insert(0, [None for _ in range(COLS)])
        self.grid = new_grid
        return cleared

    def tick(self):
        if not self.game_over:
            if not self.paused:
                self.move(0, 1)
            self.root.after(self.current_tick_ms(), self.tick)
        else:
            self.draw_game_over()

    def current_tick_ms(self):
        speed = BASE_TICK_MS - (self.level - 1) * 40
        return max(MIN_TICK_MS, speed)

    def draw(self):
        self.canvas.delete("all")
        # Grid cells
        for y in range(ROWS):
            for x in range(COLS):
                color = self.grid[y][x]
                if color:
                    self.draw_cell(x, y, color)
        # Current piece
        for x, y in self.blocks():
            self.draw_cell(x, y, COLORS[self.current])
        # Grid lines
        for x in range(COLS + 1):
            px = x * CELL_SIZE
            self.canvas.create_line(px, 0, px, ROWS * CELL_SIZE, fill="#222")
        for y in range(ROWS + 1):
            py = y * CELL_SIZE
            self.canvas.create_line(0, py, COLS * CELL_SIZE, py, fill="#222")
        self.draw_side_panels()

    def draw_cell(self, x, y, color):
        x0 = x * CELL_SIZE
        y0 = y * CELL_SIZE
        x1 = x0 + CELL_SIZE
        y1 = y0 + CELL_SIZE
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="#000")

    def draw_piece_canvas(self, canvas, piece):
        canvas.delete("all")
        if not piece:
            return
        shape = SHAPES[piece][0]
        size = 20
        offset_x = 2
        offset_y = 2
        for x, y in shape:
            x0 = (x + offset_x) * size
            y0 = (y + offset_y) * size
            x1 = x0 + size
            y1 = y0 + size
            canvas.create_rectangle(x0, y0, x1, y1, fill=COLORS[piece], outline="#000")

    def draw_side_panels(self):
        self.draw_piece_canvas(self.next_canvas, self.next_piece)
        self.draw_piece_canvas(self.hold_canvas, self.held_piece)

    def draw_game_over(self):
        self.draw()
        self.canvas.create_rectangle(0, 0, COLS * CELL_SIZE, ROWS * CELL_SIZE, fill="#000", stipple="gray25")
        self.canvas.create_text(
            COLS * CELL_SIZE / 2,
            ROWS * CELL_SIZE / 2,
            text="GAME OVER",
            fill="#fff",
            font=("Helvetica", 24, "bold"),
        )

    def toggle_pause(self):
        if self.game_over:
            return
        self.paused = not self.paused
        self.pause_var.set("Paused" if self.paused else "")

    def restart(self):
        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.score = 0
        self.level = 1
        self.lines = 0
        self.game_over = False
        self.paused = False
        self.current = None
        self.next_piece = None
        self.held_piece = None
        self.hold_used = False
        self.current_pos = (0, 0)
        self.rotation = 0
        self.bag = []
        self.score_var.set("Score: 0")
        self.level_var.set("Level: 1")
        self.lines_var.set("Lines: 0")
        self.pause_var.set("")
        self.spawn_piece()
        self.draw()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("06俄罗斯方块")
    Tetris(root)
    root.mainloop()
