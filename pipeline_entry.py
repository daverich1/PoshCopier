from __future__ import annotations

import sys

from run_pipeline import main as run_pipeline_main
from run_single_listing import main as run_single_listing_main


def main() -> None:
    if "--listing-file" in sys.argv:
        run_single_listing_main()
    else:
        run_pipeline_main()


if __name__ == "__main__":
    main()