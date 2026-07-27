import random
import tkinter as tk

TITLE = "00消消乐"
ROWS = 8
COLS = 8
CELL = 50
PADDING = 10
COLORS = [
    "#E74C3C",
    "#F1C40F",
    "#2ECC71",
    "#3498DB",
    "#E67E22",
    "#9B59B6",
]


class Match3Game:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.score = 0
        self.selected = None

        top = tk.Frame(root, padx=PADDING, pady=PADDING)
        top.pack(fill="x")
        self.score_var = tk.StringVar(value=f"得分: {self.score}")
        tk.Label(top, text=self.score_var, font=("Helvetica", 14)).pack(side="left")
        tk.Button(top, text="重开", command=self.reset).pack(side="right")

        w = COLS * CELL
        h = ROWS * CELL
        self.canvas = tk.Canvas(root, width=w, height=h, bg="#1F2A44", highlightthickness=0)
        self.canvas.pack(padx=PADDING, pady=(0, PADDING))
        self.canvas.bind("<Button-1>", self.on_click)

        self.grid = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.reset()

    def reset(self) -> None:
        self.score = 0
        self.score_var.set(f"得分: {self.score}")
        self.selected = None
        self.grid = [[random.randrange(len(COLORS)) for _ in range(COLS)] for _ in range(ROWS)]
        self.resolve_cascades()
        self.draw()

    def draw(self) -> None:
        self.canvas.delete("all")
        for r in range(ROWS):
            for c in range(COLS):
                val = self.grid[r][c]
                color = COLORS[val]
                x0 = c * CELL
                y0 = r * CELL
                x1 = x0 + CELL
                y1 = y0 + CELL
                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill=color, outline="")
        if self.selected:
            r, c = self.selected
            x0 = c * CELL
            y0 = r * CELL
            x1 = x0 + CELL
            y1 = y0 + CELL
            self.canvas.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#ECF0F1", width=3)

    def on_click(self, event: tk.Event) -> None:
        c = event.x // CELL
        r = event.y // CELL
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return
        if self.selected is None:
            self.selected = (r, c)
            self.draw()
            return
        if self.selected == (r, c):
            self.selected = None
            self.draw()
            return
        sr, sc = self.selected
        if abs(sr - r) + abs(sc - c) != 1:
            self.selected = (r, c)
            self.draw()
            return
        self.swap((sr, sc), (r, c))
        if self.find_matches():
            self.resolve_cascades()
        else:
            self.swap((sr, sc), (r, c))
        self.selected = None
        self.draw()

    def swap(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ar, ac = a
        br, bc = b
        self.grid[ar][ac], self.grid[br][bc] = self.grid[br][bc], self.grid[ar][ac]

    def find_matches(self) -> set[tuple[int, int]]:
        matches: set[tuple[int, int]] = set()
        for r in range(ROWS):
            run_start = 0
            for c in range(1, COLS + 1):
                if c < COLS and self.grid[r][c] == self.grid[r][run_start]:
                    continue
                run_len = c - run_start
                if run_len >= 3:
                    for cc in range(run_start, c):
                        matches.add((r, cc))
                run_start = c
        for c in range(COLS):
            run_start = 0
            for r in range(1, ROWS + 1):
                if r < ROWS and self.grid[r][c] == self.grid[run_start][c]:
                    continue
                run_len = r - run_start
                if run_len >= 3:
                    for rr in range(run_start, r):
                        matches.add((rr, c))
                run_start = r
        return matches

    def resolve_cascades(self) -> None:
        while True:
            matches = self.find_matches()
            if not matches:
                break
            self.score += len(matches) * 10
            self.score_var.set(f"得分: {self.score}")
            for r, c in matches:
                self.grid[r][c] = None
            self.collapse()
            self.refill()

    def collapse(self) -> None:
        for c in range(COLS):
            write_row = ROWS - 1
            for r in range(ROWS - 1, -1, -1):
                if self.grid[r][c] is not None:
                    self.grid[write_row][c] = self.grid[r][c]
                    if write_row != r:
                        self.grid[r][c] = None
                    write_row -= 1
            for r in range(write_row, -1, -1):
                self.grid[r][c] = None

    def refill(self) -> None:
        for r in range(ROWS):
            for c in range(COLS):
                if self.grid[r][c] is None:
                    self.grid[r][c] = random.randrange(len(COLORS))


def main() -> None:
    root = tk.Tk()
    Match3Game(root)
    root.mainloop()


if __name__ == "__main__":
    main()
