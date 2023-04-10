"""Module for converting and handling favicon images."""

from PIL import Image
import PIL
import PIL.IcoImagePlugin
from cairosvg import svg2png
import io

# Some helper functions.


class UnidentifiedImageError(Exception):
    """Raised when the image couldn't be identified."""

    pass


def _bytes_to_image(image: bytes) -> Image.Image:
    """Open a PIL Image with image data.

    Args:
        image: The image data.

    Returns:
        A PIL.Image.Image instance.
    """

    with io.BytesIO(image) as image_data:
        try:
            result = Image.open(image_data)
        except PIL.UnidentifiedImageError as exc:
            raise UnidentifiedImageError("Coudln't identify image") from exc
        result.load()
        return result


def _image_to_bytes(image: Image.Image, format: str = "png") -> bytes:
    """Save a PIL Image to bytes object and return it.

    Args:
        image: The PIL image.
        format: Image format to use when saving image. It's image/png by
          default because IconPair uses PNGs. Must be a string recognised by
          PIL.

    Returns:
        A bytes object.
    """

    with io.BytesIO() as image_data:
        image.save(image_data, format=format)
        return image_data.getvalue()


class IconPair:
    """This class represents 16x16 and 32x32 PNG images suitable as favicons.

    Althought this class provides a constructor, it is advised to use one of
    create_from_* classmethods to get a IconPair instance. These methods will
    automatically convert and handle images of different formats.

    Attributes:
        x16: A 16x16 PNG image saved in bytes object.
        x32: A 32x32 PNG image saved in bytes object.
    """

    def __init__(self, x16: bytes, x32: bytes):
        """Constructor for IconPair.

        create_from_* classmethods sould be the preferred method of
        initialization of the IconPair instance.

        Args:
            x16: a 16x16 PNG image saved in bytes object.
            x32: a 32x32 PNG image saved in bytes object.
        """

        self.x16, self.x32 = x16, x32

    @classmethod
    def create_from_image(cls, img: bytes) -> "IconPair":
        """Create IconPair from any image.

        This method passes the image directly to PIL which then guesses the
        image format and then processes it.

        This method musn't be used for .ico and .svg files. Use
        create_from_ico() and create_from_svg() instead.

        Args:
            png: The image to convert.

        Returns:
            A IconPair object.
        """

        image = _bytes_to_image(img)
        x16 = _image_to_bytes(image.resize((16, 16)))
        x32 = _image_to_bytes(image.resize((32, 32)))
        return cls(x16, x32)

    @classmethod
    def create_from_svg(cls, svg: bytes) -> "IconPair":
        """Create IconPair from a SVG image.

        Args:
            ico: The image to convert.

        Returns:
            A IconPair object.
        """
        x16 = svg2png(svg, output_width=16, output_height=16)
        x32 = svg2png(svg, output_width=32, output_height=32)
        assert isinstance(x16, bytes)
        assert isinstance(x32, bytes)
        return cls(x16, x32)

    @classmethod
    def create_from_ico(cls, ico: bytes) -> "IconPair":
        """Create IconPair from a ICO image.

        Args:
            ico: The image to convert.

        Returns:
            A IconPair object.
        """

        with io.BytesIO(ico) as image_data:
            images = PIL.IcoImagePlugin.IcoFile(image_data)

            sizes = images.sizes()

            # Get the largest icon for downslacing to 16x16 and 32x32 if
            # needed.
            largest = images.getimage(max(sizes))

            # Try to use the right sized icon when available, otherwise
            # downscale (or upscale).
            if (32, 32) in sizes:
                x32 = _image_to_bytes(images.getimage((32, 32)))
            else:
                x32 = _image_to_bytes(largest.resize((32, 32)))

            if (16, 16) in sizes:
                x16 = _image_to_bytes(images.getimage((16, 16)))
            else:
                x16 = _image_to_bytes(largest.resize((16, 16)))

        return cls(x16, x32)
