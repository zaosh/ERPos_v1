"""Unit tests for cv_service — does not load CLIP model."""
import numpy as np
import pytest
from unittest.mock import patch
from PIL import Image
import io


import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import services.cv_service as cv_service


def make_solid_image(rgb: tuple, size=(100, 100)) -> Image.Image:
    img = Image.new("RGB", size, rgb)
    return img


def image_to_path(img: Image.Image, tmp_path) -> str:
    p = tmp_path / "test.jpg"
    img.save(str(p), format="JPEG")
    return str(p)


class TestNearestColor:
    def test_black(self):
        assert cv_service._nearest_color(np.array([0, 0, 0])) == "black"

    def test_white(self):
        assert cv_service._nearest_color(np.array([255, 255, 255])) == "white"

    def test_red(self):
        assert cv_service._nearest_color(np.array([220, 30, 30])) == "red"

    def test_blue(self):
        result = cv_service._nearest_color(np.array([30, 70, 200]))
        assert result in ("blue", "navy")


class TestDetectColor:
    def test_black_shirt(self):
        img = make_solid_image((10, 10, 10))
        result = cv_service._detect_color(img)
        assert result == "black"

    def test_white_shirt(self):
        img = make_solid_image((250, 250, 250))
        result = cv_service._detect_color(img)
        assert result == "white"

    def test_red_shirt(self):
        img = make_solid_image((220, 30, 30))
        result = cv_service._detect_color(img)
        assert result == "red"


class TestEmptyResult:
    def test_empty_result_needs_review(self):
        result = cv_service._empty_result("test_reason")
        assert result["needs_review"] is True
        assert result["color"] is None
        assert result["type"] is None
        assert result["confidence"] == 0.0
        assert "test_reason" in result["raw_output"]["error"]


class TestAnalyzeImage:
    @pytest.mark.asyncio
    async def test_timeout_returns_needs_review(self, tmp_path):
        import asyncio
        img = make_solid_image((50, 50, 50))
        path = image_to_path(img, tmp_path)

        with patch("services.cv_service.settings") as mock_settings:
            mock_settings.CV_PROCESSING_TIMEOUT = 0.000001
            mock_settings.CV_CONFIDENCE_THRESHOLD = 0.4
            mock_settings.CV_MODEL = "test"
            result = await cv_service.analyze_image(path)

        assert result["needs_review"] is True

    @pytest.mark.asyncio
    async def test_missing_file_returns_needs_review(self):
        result = await cv_service.analyze_image("/nonexistent/path.jpg")
        assert result["needs_review"] is True
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_model_not_loaded_returns_color_only(self, tmp_path):
        img = make_solid_image((0, 0, 0))
        path = image_to_path(img, tmp_path)

        with patch.object(cv_service, "_model_loaded", False):
            result = await cv_service.analyze_image(path)

        assert result["color"] == "black"
        assert result["type"] == "unknown"
        assert result["needs_review"] is True
