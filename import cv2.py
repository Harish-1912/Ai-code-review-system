import tkinter as tk
import math

class Heart:
    def __init__(self, canvas, x, y, size):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.size = size
        self.t = 0

    def draw(self):
        points = []
        # generate points for the heart curve
        for _ in range(100):
            self.t += 0.01
            px = self.x + self.size * 16 * (math.sin(self.t) ** 3)
            py = self.y - self.size * (13 * math.cos(self.t) - 5 * math.cos(2 * self.t) -
                                        2 * math.cos(3 * self.t) - math.cos(4 * self.t))
            points.extend([px, py])
        self.canvas.create_line(points, fill='red', width=2, smooth=True)

    def animate(self):
        self.canvas.delete('all')
        self.draw()
        self.canvas.after(16, self.animate)  # ~60 FPS

root = tk.Tk()
canvas = tk.Canvas(root, width=400, height=400, bg='white')
canvas.pack()
heart = Heart(canvas, 200, 200, 1)
heart.animate()
root.mainloop()