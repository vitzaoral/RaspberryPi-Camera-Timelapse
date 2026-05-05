"""Person detection via YOLOv4-tiny + multi-stage filter for outdoor scenes.

YOLO trained on COCO over-fires on outdoor static structures (tree branches,
beehives, vertical posts). This module post-filters raw detections by
confidence, box size, aspect ratio, and a vertical zone-of-interest before
accepting them as a real person.

Tunables are constants below — change = OTA push of this file. Values picked
for Camera 1 (strom): tree foliage in upper part of frame, hives + path in
lower part, person at 5-10 m typically 100-250 px tall in full-res.
"""

import logging
import os
from dataclasses import dataclass

import cv2

logger = logging.getLogger(__name__)

# ---- Tunables ---------------------------------------------------------------
# All thresholds are in code (no config.json change possible OTA).
PERSON_CONFIDENCE_THRESHOLD = 0.6   # COCO class 0; YOLO default is 0.5
NMS_IOU_THRESHOLD = 0.4              # merge overlapping boxes for the same object
INPUT_SIZE = (416, 416)              # YOLOv4-tiny native input

# False-positive guards (Camera 1 / strom):
#   above_zone : box ends above this fraction of image height → likely tree
#   too_small  : box height < this fraction of image height   → noise / shadow
#   wrong_aspect : height/width below this → not a vertical person silhouette
DETECTION_ZONE_TOP_RATIO = 0.35
MIN_BOX_HEIGHT_RATIO = 0.08
MIN_BOX_ASPECT_RATIO = 1.3

# Debug visualization: draw rejected candidates as red boxes with reason label.
# Set False once tuning is dialed in — the gallery will only show accepted hits.
DRAW_REJECTED_CANDIDATES = True

# Drawing
ACCEPTED_COLOR_BGR = (0, 255, 0)     # green
REJECTED_COLOR_BGR = (0, 0, 255)     # red

_MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_MODEL_DIR, "yolo", "yolov4-tiny.cfg")
_WEIGHTS_PATH = os.path.join(_MODEL_DIR, "yolo", "yolov4-tiny.weights")

# ---- Module-level model cache ----------------------------------------------
# YOLO weights are ~23 MB. Loading them per call (each detection cycle) eats
# 200-400 ms of disk I/O on a Pi Zero 2 W. With detection re-firing every 1 s
# in continuous-monitoring mode, that adds up fast. Load once, reuse.
_NET = None
_OUTPUT_LAYERS = None


def _get_net():
    global _NET, _OUTPUT_LAYERS
    if _NET is not None:
        return _NET, _OUTPUT_LAYERS
    try:
        net = cv2.dnn.readNetFromDarknet(_CONFIG_PATH, _WEIGHTS_PATH)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        layer_names = net.getLayerNames()
        output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
    except cv2.error as e:
        logger.exception("YOLO model load failed: %s", e)
        return None, None
    _NET = net
    _OUTPUT_LAYERS = output_layers
    logger.info("YOLO model loaded and cached")
    return _NET, _OUTPUT_LAYERS


# ---- Data --------------------------------------------------------------------


@dataclass
class Detection:
    """Single person candidate — raw or filtered.

    `box` is (x, y, w, h) in pixel coordinates of the input image.
    `rejected_reason` is None for accepted detections; one of
    "low_conf" / "above_zone" / "too_small" / "wrong_aspect" otherwise.
    """
    box: tuple
    confidence: float
    rejected_reason: str = None


# ---- Detection ---------------------------------------------------------------


def _evaluate_box(box, confidence, image_h, image_w):
    """Return rejection reason or None if the box passes all filters."""
    x, y, w, h = box
    if confidence < PERSON_CONFIDENCE_THRESHOLD:
        return "low_conf"
    if h < image_h * MIN_BOX_HEIGHT_RATIO:
        return "too_small"
    if h / max(w, 1) < MIN_BOX_ASPECT_RATIO:
        return "wrong_aspect"
    if (y + h) < image_h * DETECTION_ZONE_TOP_RATIO:
        return "above_zone"
    return None


def detect_persons(image_path):
    """Run YOLO + multi-stage filter on an image file.

    Returns (image, accepted, rejected) where image is the loaded ndarray
    (None if load failed) and the two lists hold Detection objects.
    """
    net, output_layers = _get_net()
    if net is None:
        return None, [], []

    image = cv2.imread(image_path)
    if image is None:
        logger.warning("Image not found or invalid: %s", image_path)
        return None, [], []

    image_h, image_w = image.shape[:2]
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, INPUT_SIZE, swapRB=True, crop=False)
    net.setInput(blob)
    outputs = net.forward(output_layers)

    # Collect raw person-class candidates. We use scores[0] directly (COCO
    # class 0 = person) instead of argmax — the previous argmax approach would
    # silently drop a valid person detection if any other class scored higher
    # on the same anchor (e.g. a horse at conf 0.6 masking a person at 0.55).
    boxes = []
    confidences = []
    for output in outputs:
        for detection in output:
            # detection layout: [cx, cy, w, h, objectness, class_0, class_1, ...]
            # COCO class 0 = person. Read the person score directly (matches the
            # OpenCV YOLO sample convention) instead of argmax-ing over all
            # classes — the previous argmax approach silently dropped a valid
            # person detection if any other class scored higher on the same
            # anchor (e.g. horse 0.6 masking person 0.55).
            person_confidence = float(detection[5])
            if person_confidence <= 0.05:
                continue
            box_norm = detection[0:4] * [image_w, image_h, image_w, image_h]
            (cx, cy, w, h) = box_norm.astype("int")
            x = int(cx - w / 2)
            y = int(cy - h / 2)
            boxes.append([x, y, int(w), int(h)])
            confidences.append(person_confidence)

    # NMS to merge overlapping boxes for the same physical person.
    accepted, rejected = [], []
    if boxes:
        indices = cv2.dnn.NMSBoxes(
            boxes, confidences,
            score_threshold=0.05,           # keep low so weak candidates still go through filter pipeline below
            nms_threshold=NMS_IOU_THRESHOLD,
        )
        # OpenCV returns list of int (newer) or 2D ndarray (older).
        if len(indices) > 0:
            flat_indices = (
                indices.flatten().tolist() if hasattr(indices, "flatten") else list(indices)
            )
            for i in flat_indices:
                box = tuple(boxes[i])
                conf = confidences[i]
                reason = _evaluate_box(box, conf, image_h, image_w)
                det = Detection(box=box, confidence=conf, rejected_reason=reason)
                if reason is None:
                    accepted.append(det)
                else:
                    rejected.append(det)

    logger.info(
        "Detection: accepted=%d (max_conf=%.2f) rejected=%d (reasons=%s)",
        len(accepted),
        max((d.confidence for d in accepted), default=0.0),
        len(rejected),
        ",".join(sorted({d.rejected_reason for d in rejected})) or "none",
    )

    return image, accepted, rejected


# ---- Drawing -----------------------------------------------------------------


def _box_thickness(image_h):
    """Stroke width that scales with image size — 1 px is invisible on 12 MP."""
    return max(2, image_h // 400)


def _draw_box(image, box, color, label):
    x, y, w, h = box
    image_h = image.shape[0]
    thickness = _box_thickness(image_h)
    font_scale = max(0.6, image_h / 1200)
    font_thickness = max(1, thickness // 2)

    cv2.rectangle(image, (x, y), (x + w, y + h), color, thickness)

    # Label with filled background so it's readable on any backdrop.
    (label_w, label_h), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
    )
    label_y = max(label_h + 4, y - 4)
    cv2.rectangle(
        image,
        (x, label_y - label_h - baseline - 2),
        (x + label_w + 6, label_y + 2),
        color,
        thickness=cv2.FILLED,
    )
    cv2.putText(
        image,
        label,
        (x + 3, label_y - 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (0, 0, 0),
        font_thickness,
        cv2.LINE_AA,
    )


def draw_detections(image, accepted, rejected=None):
    """Draw accepted detections (green) and optionally rejected candidates
    (red, with rejection-reason label) for tuning.
    """
    for det in accepted:
        _draw_box(image, det.box, ACCEPTED_COLOR_BGR, f"Person {det.confidence:.2f}")

    if DRAW_REJECTED_CANDIDATES and rejected:
        for det in rejected:
            _draw_box(
                image,
                det.box,
                REJECTED_COLOR_BGR,
                f"{det.rejected_reason} {det.confidence:.2f}",
            )

    # Visualize the zone-of-interest cutoff as a faint horizontal line so the
    # `above_zone` reasoning is obvious in the gallery.
    if DRAW_REJECTED_CANDIDATES:
        h, w = image.shape[:2]
        zone_y = int(h * DETECTION_ZONE_TOP_RATIO)
        cv2.line(image, (0, zone_y), (w, zone_y), (255, 255, 0), max(1, h // 800))

    return image


# ---- Backwards-compat wrapper -----------------------------------------------


def detect_and_draw_person(image_path):
    """Legacy entry point used by main.py before this rewrite. Keeps the same
    signature (returns bool, writes annotated image back to image_path) so an
    OTA push of just this file still works without main.py changes.

    Prefer detect_persons() + draw_detections() for new code — it returns the
    confidence values that we want to upload as Cloudinary tags.
    """
    image, accepted, rejected = detect_persons(image_path)
    if image is None:
        return False
    if accepted or (DRAW_REJECTED_CANDIDATES and rejected):
        image = draw_detections(image, accepted, rejected)
        cv2.imwrite(image_path, image)
    return bool(accepted)
