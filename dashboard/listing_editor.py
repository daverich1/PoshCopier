from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from inventory.inventory_item import InventoryItem


class ListingEditor(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        item: InventoryItem,
        *,
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)

        self.item = item
        self.on_saved = on_saved
        self.payload = self._load_listing()

        self.title(
            f"Edit Listing - {item.title or item.listing_id}"
        )
        self.geometry("760x760")
        self.minsize(680, 660)
        self.transient(parent)
        self.grab_set()

        self.title_var = tk.StringVar(
            value=str(
                self.payload.get("title", "")
            )
        )
        self.brand_var = tk.StringVar(
            value=str(
                self.payload.get("brand", "")
            )
        )
        self.price_var = tk.StringVar(
            value=str(
                self.payload.get("price", "")
            )
        )
        self.size_var = tk.StringVar(
            value=self._initial_size()
        )
        self.category_var = tk.StringVar(
            value=str(
                self.payload.get("category", "")
            )
        )
        self.condition_var = tk.StringVar(
            value=str(
                self.payload.get("condition", "")
            )
        )
        self.status_var = tk.StringVar(
            value=f"Editing {item.listing_path.name}"
        )

        self._build_interface()
        self.protocol(
            "WM_DELETE_WINDOW",
            self.close,
        )

        self.after(
            50,
            self._focus_title,
        )

    def _build_interface(self) -> None:
        main = ttk.Frame(
            self,
            padding=16,
        )
        main.pack(
            fill="both",
            expand=True,
        )

        main.columnconfigure(
            1,
            weight=1,
        )
        main.rowconfigure(
            7,
            weight=1,
        )

        ttk.Label(
            main,
            text="Edit Listing",
            font=("Segoe UI", 18, "bold"),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 14),
        )

        self._add_entry_row(
            main,
            row=1,
            label="Title:",
            variable=self.title_var,
        )
        self._add_entry_row(
            main,
            row=2,
            label="Brand:",
            variable=self.brand_var,
        )
        self._add_entry_row(
            main,
            row=3,
            label="Price:",
            variable=self.price_var,
        )
        self._add_entry_row(
            main,
            row=4,
            label="Size:",
            variable=self.size_var,
        )
        self._add_entry_row(
            main,
            row=5,
            label="Category:",
            variable=self.category_var,
        )

        ttk.Label(
            main,
            text="Condition:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=6,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=5,
        )

        self.condition_combo = ttk.Combobox(
            main,
            textvariable=self.condition_var,
            values=(
                "New with tags",
                "New without tags",
                "Like new",
                "Good",
                "Fair",
            ),
            state="normal",
        )
        self.condition_combo.grid(
            row=6,
            column=1,
            sticky="ew",
            pady=5,
        )

        ttk.Label(
            main,
            text="Description:",
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=7,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=(6, 0),
        )

        description_frame = ttk.Frame(
            main
        )
        description_frame.grid(
            row=7,
            column=1,
            sticky="nsew",
            pady=(6, 0),
        )
        description_frame.columnconfigure(
            0,
            weight=1,
        )
        description_frame.rowconfigure(
            0,
            weight=1,
        )

        self.description_text = tk.Text(
            description_frame,
            wrap="word",
            font=("Segoe UI", 10),
            undo=True,
        )
        self.description_text.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        description_scrollbar = ttk.Scrollbar(
            description_frame,
            orient="vertical",
            command=self.description_text.yview,
        )
        description_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.description_text.configure(
            yscrollcommand=description_scrollbar.set,
        )

        self.description_text.insert(
            "1.0",
            str(
                self.payload.get(
                    "description",
                    "",
                )
            ),
        )

        actions = ttk.Frame(
            main
        )
        actions.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 0),
        )

        ttk.Button(
            actions,
            text="Save",
            command=self.save,
        ).pack(
            side="left",
        )

        ttk.Button(
            actions,
            text="Cancel",
            command=self.close,
        ).pack(
            side="left",
            padx=(8, 0),
        )

        ttk.Label(
            actions,
            textvariable=self.status_var,
        ).pack(
            side="right",
        )

    def _add_entry_row(
        self,
        parent: ttk.Frame,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(
            parent,
            text=label,
            font=("Segoe UI", 9, "bold"),
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=5,
        )

        entry = ttk.Entry(
            parent,
            textvariable=variable,
        )
        entry.grid(
            row=row,
            column=1,
            sticky="ew",
            pady=5,
        )

        if row == 1:
            self.title_entry = entry

    def _focus_title(self) -> None:
        self.title_entry.focus_set()
        self.title_entry.selection_range(
            0,
            "end",
        )

    def _load_listing(self) -> dict:
        try:
            payload = json.loads(
                self.item.listing_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(
                f"Could not load listing JSON:\n{error}"
            ) from error

        if not isinstance(
            payload,
            dict,
        ):
            raise RuntimeError(
                "Listing JSON must contain an object."
            )

        return payload

    def _initial_size(self) -> str:
        sizes = self.payload.get(
            "sizes"
        )

        if isinstance(
            sizes,
            list,
        ):
            cleaned = [
                str(value).strip()
                for value in sizes
                if str(value).strip()
            ]

            if cleaned:
                return ", ".join(
                    cleaned
                )

        return str(
            self.payload.get(
                "size",
                "",
            )
        )

    def _validated_values(self) -> dict[str, str]:
        title = self.title_var.get().strip()
        brand = self.brand_var.get().strip()
        price = self.price_var.get().strip()
        size = self.size_var.get().strip()
        category = self.category_var.get().strip()
        condition = self.condition_var.get().strip()
        description = self.description_text.get(
            "1.0",
            "end-1c",
        ).strip()

        missing = [
            label
            for label, value in (
                ("Title", title),
                ("Description", description),
                ("Price", price),
                ("Brand", brand),
                ("Category", category),
                ("Condition", condition),
                ("Size", size),
            )
            if not value
        ]

        if missing:
            raise ValueError(
                "These fields are required:\n"
                + ", ".join(missing)
            )

        return {
            "title": title,
            "brand": brand,
            "price": price,
            "size": size,
            "category": category,
            "condition": condition,
            "description": description,
        }

    def save(self) -> None:
        try:
            values = self._validated_values()
        except ValueError as error:
            messagebox.showerror(
                "Missing Information",
                str(error),
                parent=self,
            )
            return

        updated_payload = dict(
            self.payload
        )

        updated_payload["title"] = values["title"]
        updated_payload["brand"] = values["brand"]
        updated_payload["price"] = values["price"]
        updated_payload["category"] = values["category"]
        updated_payload["condition"] = values["condition"]
        updated_payload["description"] = values["description"]

        parsed_sizes = [
            value.strip()
            for value in values["size"].split(",")
            if value.strip()
        ]

        if len(parsed_sizes) > 1:
            updated_payload["sizes"] = parsed_sizes
            updated_payload["size"] = parsed_sizes[0]
            updated_payload["is_multi_size"] = True
        else:
            single_size = (
                parsed_sizes[0]
                if parsed_sizes
                else values["size"]
            )
            updated_payload["size"] = single_size
            updated_payload["sizes"] = [single_size]
            updated_payload["is_multi_size"] = False

        try:
            self._atomic_write_json(
                self.item.listing_path,
                updated_payload,
            )
        except OSError as error:
            messagebox.showerror(
                "Save Failed",
                str(error),
                parent=self,
            )
            return

        self.payload = updated_payload
        self.status_var.set(
            "Saved"
        )

        if self.on_saved is not None:
            self.on_saved()

        messagebox.showinfo(
            "Listing Saved",
            "The listing was saved successfully.",
            parent=self,
        )

        self.close()

    def _atomic_write_json(
        self,
        path: Path,
        payload: dict,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )

        try:
            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            Path(
                temporary_name
            ).replace(
                path
            )

        except Exception:
            try:
                Path(
                    temporary_name
                ).unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()
