import unittest
import io
from PIL import Image

import icon


class IconTest(unittest.TestCase):
    def test_correct_size(self):
        with open("tests/sample-data/facebook32.png", "rb") as f:
            data = f.read()
        new_icon = icon.IconPair.create_from_image(data)

        with io.BytesIO(new_icon.x32) as f:
            x32 = Image.open(f)
            self.assertEqual(x32.size, (32, 32))

        with io.BytesIO(new_icon.x16) as f:
            x16 = Image.open(f)
            self.assertEqual(x16.size, (16, 16))
