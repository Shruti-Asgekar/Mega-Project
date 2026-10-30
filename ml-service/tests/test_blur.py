"""
Unit Tests for Blur Detection in ml-service.
"""

import io
import numpy as np
import cv2
from PIL import Image
from services.blur import calculate_blur_score

def test_sharp_image_blur_score():
    # Create sharp synthetic image with high gradient checkerboard
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[::4, ::4] = 255
    pil_img = Image.fromarray(img)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    data = buf.getvalue()

    res = calculate_blur_score(data, filename="sharp.png", blur_threshold=100.0)
    assert res["blur_score"] > 100.0
    assert res["is_blurry"] is False

def test_blurry_image_blur_score():
    # Create heavy blurred image
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[::4, ::4] = 255
    blurred = cv2.GaussianBlur(img, (21, 21), 0)
    pil_img = Image.fromarray(blurred)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=80)
    data = buf.getvalue()

    res = calculate_blur_score(data, filename="blurry.jpg", blur_threshold=100.0)
    assert res["blur_score"] < 100.0
    assert res["is_blurry"] is True
