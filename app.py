from __future__ import annotations

import tkinter as tk

from dashboard.dashboard import PoshCopierDashboard


def main() -> None:
    root = tk.Tk()
    PoshCopierDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()