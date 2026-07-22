"""Entry point for the pixel ecosystem game.

Run with:
    uv run python main.py
"""

from __future__ import annotations

import tkinter as tk

from ecosystem.ui.app import EcosystemApp


def main() -> None:
    root = tk.Tk()
    EcosystemApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
