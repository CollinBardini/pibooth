# -*- coding: utf-8 -*-

import time
from numpy import rot90
import pygame
try:
    from picamera2 import Picamera2
    import libcamera
except ImportError:
    Picamera2 = None  # Picamera2 & libcamera optional
    libcamera = None
from PIL import Image, ImageFilter
from pibooth.pictures import sizing
from pibooth.utils import PoolingTimer, LOGGER
from pibooth.language import get_translated_text
from pibooth.camera.base import BaseCamera


def get_rpi_camera_2_proxy(port=None):
    """Return camera proxy if a Raspberry Pi compatible camera is found
    else return None.

    :param port: look on given port number
    :type port: int
    """
    if not Picamera2 or not libcamera:
        return None  # Picamera2 or libcamera is not installed
    try:
        picam2 = Picamera2()
        return picam2
    except OSError:
        pass
    return None


class RpiCamera2(BaseCamera):

    """RpiCamera2 camera management.
    """

    IMAGE_EFFECTS = [u'none',
                     u'blur',
                     u'contour',
                     u'detail',
                     u'edge_enhance',
                     u'edge_enhance_more',
                     u'emboss',
                     u'find_edges',
                     u'smooth',
                     u'smooth_more',
                     u'sharpen']

    def __init__(self, camera_proxy):
        super(RpiCamera2, self).__init__(camera_proxy)
        self._overlay_alpha = 255

    def _specific_initialization(self):
        """Camera initialization.
        """
        controls = {'ExposureTime': self.preview_iso*1000}
        transform = libcamera.Transform(hflip=self.preview_flip, vflip=False, rotation=self.preview_rotation)
        main = {'size': (max(self.resolution), min(self.resolution)), 'format': 'BGR888'}
        preview_config = self._cam.preview_configuration(main = main, controls=controls, transform=transform)
        self._cam.configure(preview_config)
        self._cam.start()
        
    def _show_overlay(self, text, alpha):
        """Add an image as an overlay.
        """
        if self._window:  # No window means no preview displayed
            rect = self.get_rect()
            self._overlay_alpha = alpha
            self._overlay = self.build_overlay((rect.width, rect.height), str(text), alpha)

    def _get_preview_image(self):
        """Capture a new preview image.
        """
        rect = self.get_rect()

        data = self._cam.capture_array()
        image = Image.fromarray(data)

        # Crop to keep aspect ratio of the resolution
        image = image.crop(sizing.new_size_by_croping_ratio(image.size, self.resolution))
        # Resize to fit the available space in the window
        image = image.resize(sizing.new_size_keep_aspect_ratio(image.size, (rect.width, rect.height), 'outer'))

        if self.preview_flip:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if self._overlay:
            image.paste(self._overlay, (0, 0), self._overlay)
        return image

    def _post_process_capture(self, capture_data):
        """Rework capture data.

        :param capture_data: couple (frame, effect)
        :type capture_data: tuple
        """
        frame, effect = capture_data
        image = Image.fromarray(frame)

        # Crop to keep aspect ratio of the resolution
        image = image.crop(sizing.new_size_by_croping_ratio(image.size, self.resolution))
        # Resize to fit the resolution
        image = image.resize(sizing.new_size_keep_aspect_ratio(image.size, self.resolution, 'outer'))

        if self.capture_flip:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        if effect != 'none':
            image = image.filter(getattr(ImageFilter, effect.upper()))

        #image = image.convert('RGB')

        return image

    def preview(self, window, flip=True):
        """Setup the preview.
        """
        self._window = window
        self.preview_flip = flip
        self._window.show_image(self._get_preview_image())

    def preview_countdown(self, timeout, alpha=80):
        """Show a countdown of `timeout` seconds on the preview.
        Returns when the countdown is finished.
        """
        timeout = int(timeout)
        if timeout < 1:
            raise ValueError("Start time shall be greater than 0")

        timer = PoolingTimer(timeout)
        while not timer.is_timeout():
            remaining = int(timer.remaining() + 1)
            if self._overlay is None or remaining != timeout:
                # Rebluid overlay only if remaining number has changed
                self._show_overlay(str(remaining), alpha)
                timeout = remaining

            updated_rect = self._window.show_image(self._get_preview_image())
            pygame.event.pump()
            if updated_rect:
                pygame.display.update(updated_rect)

        self._show_overlay(get_translated_text('smile'), alpha)
        self._window.show_image(self._get_preview_image())

    def preview_wait(self, timeout, alpha=80):
        """Wait the given time.
        """
        timeout = int(timeout)
        if timeout < 1:
            raise ValueError("Start time shall be greater than 0")

        timer = PoolingTimer(timeout)
        while not timer.is_timeout():
            updated_rect = self._window.show_image(self._get_preview_image())
            pygame.event.pump()
            if updated_rect:
                pygame.display.update(updated_rect)

        self._show_overlay(get_translated_text('smile'), alpha)
        self._window.show_image(self._get_preview_image())

    def stop_preview(self):
        """Stop the preview.
        """
        self._hide_overlay()
        self._window = None

    def capture(self, effect=None):
        """Capture a new picture.
        """
        effect = str(effect).lower()
        if effect not in self.IMAGE_EFFECTS:
            raise ValueError("Invalid capture effect '{}' (choose among {})".format(effect, self.IMAGE_EFFECTS))

        if self.capture_iso != self.preview_iso:
            self._cam.set_controls({'ExposureTime': self.capture_iso*1000})

        LOGGER.debug("Taking capture at resolution %s", self.resolution)

        data = self._cam.capture_array()

        if self.capture_iso != self.preview_iso: 
            self._cam.set_controls({'ExposureTime': self.preview_iso*1000})

        self._captures.append((data, effect))

        time.sleep(0.5)  # To let time to see "Smile"

        self._hide_overlay()  # If stop_preview() has not been called

    def quit(self):
        """Close the camera driver, it's definitive.
        """
        if self._cam:
            self._cam.stop()
