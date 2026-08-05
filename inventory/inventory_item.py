from dataclasses import dataclass
from pathlib import Path


@dataclass
class InventoryItem:
    listing_id: str
    title: str
    brand: str
    price: str
    size: str
    category: str
    image_path: Path | None
    listing_path: Path
    uploaded: bool = False
    duplicate: bool = False
    failed: bool = False
    