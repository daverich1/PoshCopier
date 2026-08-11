"""Focused tests for guarded combined-size inventory selection."""

import unittest

from uploader.multi_size import (
    INVENTORY_QUANTITY_INPUT_SELECTOR,
    row_text_matches_size,
)


class MultiSizeInventoryTests(unittest.TestCase):
    def test_single_letter_size_does_not_match_unrelated_text(self):
        self.assertFalse(row_text_matches_size("Photos & Video", "S"))
        self.assertTrue(row_text_matches_size("S 1 0", "S"))

    def test_multi_character_sizes_match_complete_tokens(self):
        self.assertTrue(row_text_matches_size("XS 1 0", "XS"))
        self.assertTrue(row_text_matches_size("10.5 1 0", "10.5"))
        self.assertFalse(row_text_matches_size("XS 1 0", "S"))

    def test_quantity_selector_cannot_select_file_inputs(self):
        self.assertNotIn('input"', INVENTORY_QUANTITY_INPUT_SELECTOR)
        self.assertNotIn('type="file"', INVENTORY_QUANTITY_INPUT_SELECTOR)


if __name__ == "__main__":
    unittest.main()
