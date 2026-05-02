"""Unit tests for the new multi-model CV service."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image


class TestDetectColor:
    @pytest.mark.asyncio
    async def test_black_shirt_returns_black(self, tmp_path):
        from services.cv_service import detect_color
        img_path = str(tmp_path / "black.jpg")
        Image.new("RGB", (200, 200), (10, 10, 10)).save(img_path)
        result = await detect_color(img_path)
        assert result == "black"

    @pytest.mark.asyncio
    async def test_white_shirt_returns_white(self, tmp_path):
        from services.cv_service import detect_color
        img_path = str(tmp_path / "white.jpg")
        Image.new("RGB", (200, 200), (255, 255, 255)).save(img_path)
        result = await detect_color(img_path)
        assert result == "white"

    @pytest.mark.asyncio
    async def test_navy_returns_navy(self, tmp_path):
        from services.cv_service import detect_color
        img_path = str(tmp_path / "navy.jpg")
        Image.new("RGB", (200, 200), (0, 0, 128)).save(img_path)
        result = await detect_color(img_path)
        assert result in ("navy", "blue")  # close colors


class TestQuickAnalyze:
    @pytest.mark.asyncio
    async def test_returns_phase_a_result(self, tmp_path):
        from services.cv_service import quick_analyze, PhaseAResult
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (40, 40, 80)).save(img_path)

        mock_content = json.dumps({
            "type": "band", "has_graphic": True, "confidence": 0.82, "needs_review": False,
        })
        mock_choice = MagicMock()
        mock_choice.message.content = mock_content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("services.cv_service.settings") as s:
            s.OPENAI_API_KEY = "test-key"
            s.CV_PHASE_A_MODEL = "gpt-4o-mini"
            s.CV_IMAGE_SIZE_PHASE_A = 512
            s.CV_PROCESSING_TIMEOUT = 10.0
            s.CV_CONFIDENCE_THRESHOLD = 0.4
            with patch("services.cv_service.AsyncOpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                result = await quick_analyze(img_path)

        assert isinstance(result, PhaseAResult)
        assert result.type == "band"
        assert result.has_graphic is True
        assert abs(result.confidence - 0.82) < 0.01
        assert result.model_used == "gpt-4o-mini"
        assert result.processing_ms >= 0

    @pytest.mark.asyncio
    async def test_fallback_when_no_api_key(self, tmp_path):
        from services.cv_service import quick_analyze
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (200, 200, 200)).save(img_path)

        with patch("services.cv_service.settings") as s:
            s.OPENAI_API_KEY = ""
            result = await quick_analyze(img_path)

        assert result.type == "unknown"
        assert result.model_used == "fallback"
        assert result.needs_review is True

    @pytest.mark.asyncio
    async def test_maps_pattern_to_patterned(self, tmp_path):
        from services.cv_service import quick_analyze
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (100, 100, 100)).save(img_path)

        mock_content = json.dumps({"type": "pattern", "has_graphic": False, "confidence": 0.7, "needs_review": False})
        mock_choice = MagicMock()
        mock_choice.message.content = mock_content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("services.cv_service.settings") as s:
            s.OPENAI_API_KEY = "test-key"
            s.CV_PHASE_A_MODEL = "gpt-4o-mini"
            s.CV_IMAGE_SIZE_PHASE_A = 512
            s.CV_PROCESSING_TIMEOUT = 10.0
            s.CV_CONFIDENCE_THRESHOLD = 0.4
            with patch("services.cv_service.AsyncOpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                result = await quick_analyze(img_path)

        assert result.type == "patterned"

    @pytest.mark.asyncio
    async def test_fallback_on_api_exception(self, tmp_path):
        from services.cv_service import quick_analyze
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (50, 50, 50)).save(img_path)

        with patch("services.cv_service.settings") as s:
            s.OPENAI_API_KEY = "test-key"
            s.CV_PHASE_A_MODEL = "gpt-4o-mini"
            s.CV_IMAGE_SIZE_PHASE_A = 512
            s.CV_PROCESSING_TIMEOUT = 10.0
            s.CV_CONFIDENCE_THRESHOLD = 0.4
            with patch("services.cv_service.AsyncOpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
                result = await quick_analyze(img_path)

        assert result.model_used == "fallback"
        assert result.type == "unknown"


class TestDeepAnalyze:
    @pytest.mark.asyncio
    async def test_returns_phase_b_result(self, tmp_path):
        from services.cv_service import deep_analyze, PhaseBResult
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (200, 200), (50, 50, 50)).save(img_path)

        mock_content = json.dumps({
            "label": "Metallica", "graphic_description": "Band logo", "style_era": "1990s",
            "visible_text": ["Metallica"], "condition_notes": None,
            "resale_interest": "high", "resale_reason": "Popular vintage band tee",
        })
        mock_choice = MagicMock()
        mock_choice.message.content = mock_content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("services.cv_service.settings") as s:
            s.OPENAI_API_KEY = "test-key"
            s.CV_PHASE_B_MODEL = "gpt-4o"
            s.CV_IMAGE_SIZE_PHASE_B = 768
            s.CV_PROCESSING_TIMEOUT = 10.0
            s.CV_CONFIDENCE_THRESHOLD = 0.4
            with patch("services.cv_service.AsyncOpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                result = await deep_analyze(img_path)

        assert isinstance(result, PhaseBResult)
        assert result.label == "Metallica"
        assert result.resale_interest == "high"
        assert result.style_era == "1990s"
        assert result.processing_ms >= 0


class TestAnalyzeFashion:
    @pytest.mark.asyncio
    async def test_returns_fashion_result(self, tmp_path):
        from services.cv_service import analyze_fashion, FashionResult
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (80, 80, 80)).save(img_path)

        hf_resp = [{"label": "oversized", "score": 0.8}, {"label": "regular", "score": 0.2}]

        with patch("services.cv_service.settings") as s:
            s.HUGGINGFACE_API_KEY = "test-hf-key"
            s.CV_FASHION_MODEL = "patrickjohncyh/fashion-clip"
            s.CV_IMAGE_SIZE_PHASE_A = 512
            s.CV_PROCESSING_TIMEOUT = 10.0
            with patch("httpx.AsyncClient") as mock_http:
                mock_instance = MagicMock()
                mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = hf_resp
                mock_instance.post = AsyncMock(return_value=mock_resp)
                result = await analyze_fashion(img_path)

        assert isinstance(result, FashionResult)
        assert result.fit == "oversized"

    @pytest.mark.asyncio
    async def test_null_result_on_timeout_never_raises(self, tmp_path):
        """analyze_fashion MUST NOT raise — returns null FashionResult on any failure."""
        from services.cv_service import analyze_fashion, FashionResult
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (100, 100, 100)).save(img_path)

        with patch("services.cv_service.settings") as s:
            s.HUGGINGFACE_API_KEY = "test-hf-key"
            s.CV_FASHION_MODEL = "patrickjohncyh/fashion-clip"
            s.CV_IMAGE_SIZE_PHASE_A = 512
            s.CV_PROCESSING_TIMEOUT = 10.0
            with patch("httpx.AsyncClient") as mock_http:
                mock_instance = MagicMock()
                mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.post = AsyncMock(side_effect=Exception("network timeout"))
                result = await analyze_fashion(img_path)

        assert isinstance(result, FashionResult)
        assert result.fit is None
        assert result.style is None
        assert result.model_used == "failed"

    @pytest.mark.asyncio
    async def test_skipped_when_no_api_key(self, tmp_path):
        from services.cv_service import analyze_fashion
        img_path = str(tmp_path / "test.jpg")
        Image.new("RGB", (100, 100), (100, 100, 100)).save(img_path)

        with patch("services.cv_service.settings") as s:
            s.HUGGINGFACE_API_KEY = ""
            result = await analyze_fashion(img_path)

        assert result.model_used == "skipped"
        assert result.fit is None


class TestGenerateZpl:
    def test_generate_zpl_contains_barcode(self):
        from services.printer_service import generate_zpl
        from models.item import ItemType

        class FakeItem:
            id = 123
            barcode = "THR-20260502-00001"
            price = __import__('decimal').Decimal("12.50")
            color = "black"
            type = ItemType.band

        zpl = generate_zpl(FakeItem())
        assert "THR-20260502-00001" in zpl
        assert "$12.50" in zpl
        assert "^XA" in zpl
        assert "^XZ" in zpl
