"""
CV Service — Image analysis using CLIP (classification) + K-means (color).
Model loads once at startup. Never reload per-request — it's expensive.

Accuracy targets:
  - Color: ~85%
  - Category type: ~70%
  - Specific label: ~40% (human fills this gap)

If confidence < CV_CONFIDENCE_THRESHOLD → set needs_review=True.
Always store raw CV output in cv_raw_output column for debugging/training.
"""
import asyncio
import logging
from typing import Optional
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

from config import settings

logger = logging.getLogger(__name__)

# Global model handles — loaded once at startup
_clip_model = None
_clip_preprocess = None
_model_loaded = False

# ─── Classification prompts ────────────────────────────────────────────────────
# Edit these to improve accuracy. Each string describes a shirt type.
# More specific = higher accuracy but narrower coverage.

CATEGORY_PROMPTS = [
    "a band or music graphic t-shirt with band logo",
    "an anime or manga graphic t-shirt",
    "a sports team jersey or t-shirt",
    "a plain solid color t-shirt with no graphic",
    "a vintage or retro graphic t-shirt",
    "a holiday christmas novelty t-shirt",
    "a branded fashion logo t-shirt like nike or adidas",
    "a tie dye or abstract pattern t-shirt",
    "a political or statement text t-shirt",
]

CATEGORY_LABELS = [
    "band",
    "anime",
    "sports",
    "plain",
    "vintage_graphic",
    "holiday",
    "branded",
    "pattern",
    "statement",
]

# Named color mapping — expand as needed
NAMED_COLORS = {
    "black":   [0, 0, 0],
    "white":   [255, 255, 255],
    "grey":    [128, 128, 128],
    "red":     [220, 30, 30],
    "blue":    [30, 70, 200],
    "navy":    [0, 0, 128],
    "green":   [30, 150, 50],
    "yellow":  [240, 200, 0],
    "orange":  [240, 100, 0],
    "pink":    [240, 100, 150],
    "purple":  [120, 30, 180],
    "brown":   [120, 70, 30],
    "beige":   [220, 190, 150],
]


async def load_cv_model():
    """Load CLIP model at startup. Call once from main.py lifespan."""
    global _clip_model, _clip_preprocess, _model_loaded
    
    if _model_loaded:
        return

    try:
        import torch
        import clip

        logger.info(f"Loading CV model: {settings.CV_MODEL}")
        loop = asyncio.get_event_loop()
        
        # Load in executor — CPU-bound
        def _load():
            return clip.load(settings.CV_MODEL, device="cpu")

        _clip_model, _clip_preprocess = await loop.run_in_executor(None, _load)
        _model_loaded = True
        logger.info("CV model loaded successfully")

    except ImportError:
        logger.warning("CLIP not installed. CV will return empty suggestions. Install: pip install clip")
    except Exception as e:
        logger.error(f"Failed to load CV model: {e}")
        # Don't crash the app — CV is optional, human always confirms


async def analyze_image(image_path: str) -> dict:
    """
    Analyze a shirt image. Returns color, type, confidence, and raw output.
    
    Returns:
        {
            "color": "black",
            "type": "band",
            "confidence": 0.72,
            "needs_review": False,
            "raw_output": { ... }  # stored for debugging
        }
    """
    try:
        async with asyncio.timeout(settings.CV_PROCESSING_TIMEOUT):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _analyze_sync, image_path)
    except asyncio.TimeoutError:
        logger.warning(f"CV processing timed out for {image_path}")
        return _empty_result(reason="timeout")
    except Exception as e:
        logger.error(f"CV analysis failed: {e}")
        return _empty_result(reason=str(e))


def _analyze_sync(image_path: str) -> dict:
    """Synchronous CV analysis — runs in thread executor."""
    img = Image.open(image_path).convert("RGB")
    
    # Remove white background for cleaner analysis
    masked_img = _remove_background(img)
    
    color = _detect_color(masked_img)
    type_result = _classify_type(img) if _model_loaded else {"label": "unknown", "confidence": 0.0}

    confidence = type_result["confidence"]

    return {
        "color": color,
        "type": type_result["label"],
        "confidence": round(confidence, 3),
        "needs_review": confidence < settings.CV_CONFIDENCE_THRESHOLD,
        "raw_output": {
            "color_analysis": color,
            "type_scores": type_result.get("all_scores", {}),
            "model": settings.CV_MODEL,
        }
    }


def _detect_color(img: Image.Image) -> str:
    """K-means color detection — returns most dominant named color."""
    # Resize for speed
    small = img.resize((100, 100))
    pixels = np.array(small).reshape(-1, 3).astype(float)

    # Remove near-white pixels (background remnants)
    non_white_mask = ~(np.all(pixels > 230, axis=1))
    if non_white_mask.sum() < 50:
        return "white"

    pixels = pixels[non_white_mask]

    # K-means with k=3 to find dominant color clusters
    k = min(3, len(pixels))
    kmeans = KMeans(n_clusters=k, n_init=3, random_state=42)
    kmeans.fit(pixels)

    # Most common cluster
    counts = np.bincount(kmeans.labels_)
    dominant_rgb = kmeans.cluster_centers_[counts.argmax()]

    return _nearest_color(dominant_rgb)


def _nearest_color(rgb: np.ndarray) -> str:
    """Map RGB to nearest named color."""
    min_dist = float("inf")
    best_name = "unknown"

    for name, ref_rgb in NAMED_COLORS.items():
        dist = np.linalg.norm(rgb - np.array(ref_rgb))
        if dist < min_dist:
            min_dist = dist
            best_name = name

    return best_name


def _classify_type(img: Image.Image) -> dict:
    """CLIP zero-shot classification — returns category label + confidence."""
    if not _model_loaded:
        return {"label": "unknown", "confidence": 0.0, "all_scores": {}}

    import torch
    import clip

    image_tensor = _clip_preprocess(img).unsqueeze(0)
    text_tokens = clip.tokenize(CATEGORY_PROMPTS)

    with torch.no_grad():
        img_features = _clip_model.encode_image(image_tensor)
        txt_features = _clip_model.encode_text(text_tokens)
        logits = (img_features @ txt_features.T).softmax(dim=-1)

    probs = logits[0].numpy()
    best_idx = probs.argmax()

    all_scores = {CATEGORY_LABELS[i]: round(float(probs[i]), 3) for i in range(len(CATEGORY_LABELS))}

    return {
        "label": CATEGORY_LABELS[best_idx],
        "confidence": float(probs[best_idx]),
        "all_scores": all_scores,
    }


def _remove_background(img: Image.Image) -> Image.Image:
    """Simple white background removal via threshold."""
    import cv2

    img_array = np.array(img)
    # Threshold: pixels where all channels > 240 = background
    mask = np.all(img_array > 240, axis=2)
    img_array[mask] = [128, 128, 128]  # replace with neutral grey
    return Image.fromarray(img_array)


def _empty_result(reason: str = "unknown") -> dict:
    """Return empty CV result when analysis fails."""
    return {
        "color": None,
        "type": None,
        "confidence": 0.0,
        "needs_review": True,
        "raw_output": {"error": reason},
    }
