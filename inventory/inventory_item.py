from dataclasses import dataclass, field
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

    # ---------- Inventory Health ----------

    health_status: str = "Unknown"

    ready_for_upload: bool = False

    health_messages: list[str] = field(
        default_factory=list
    )