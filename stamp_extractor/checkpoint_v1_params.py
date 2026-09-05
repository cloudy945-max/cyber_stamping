"""
stamp_extractor / CHECKPOINT v1
===============================
Snapshot taken after user confirmed "棋盘格预览图是我希望要的效果" (2026-08-29)
but BEFORE adding the "stamp outer-edge region forced-drop" post-processing
step for chat-screenshot inputs (img1..3 jfif).

Purpose: if later tuning / region-drop / new presets regress quality on
8181.HEIC or any case, the exact defaults/pipeline here can be restored by:

    from stamp_extractor.checkpoint_v1_params import V1_CONFIG_PRESETS, V1_PIPELINE_STEPS
    cfg = ExtractorConfig(**V1_CONFIG_PRESETS["default"])   # or conservative / preserve_light

The key invariants of V1:
  * RGB untouched in final RGBA. Only Alpha is computed.
  * Alpha is CONTINUOUS (smoothstep), never binary thresholded.
  * No morphology (close / dilate / erode), no fill-holes, no sharpen, no resample-down.
  * Lab colorspace in REAL perceptual encoding: L in [0,100], a,b in [-128,127]
    (NOT the OpenCV uint8 packed 0..255 Lab). See utils.rgb_uint8_to_lab_float.
  * Paper model is estimated FROM THE SAME NORMALIZED Lab float that is used to
    compute ink distances (local luminance correction runs first, THEN paper
    estimate; corrected the earlier "apple vs oranges" space mismatch that made
    nontransparent_pct incorrectly report ~99%).
  * locate_stamp_subregion_bbox pre-crops chat screenshots to the coloured
    stamp-containing square but does NOT decide final bbox (that is still done
    from Alpha>threshold post-hoc).
  * noise_min_area == 0 by DEFAULT (principle 6: preserve raw defects).
  * internal blank paper areas are transparent because every pixel is scored
    independently; there is NO flood-fill / inside-contour-fill step.
"""

from __future__ import annotations

V1_CONFIG_PRESETS = {
    # ------------------------------ default ---------------------------------
    # Balanced. Tuned so that:
    #   img1 (faint orange-red circular):   opaque ~41%,  nontransparent ~67%
    #   img2 (large saturated red rect):    opaque ~67%,  nontransparent ~90%
    #   img3 (complex outer-ring stamp):    opaque ~64%,  nontransparent ~87%
    #   8181.HEIC (red oval stamp photo):   opaque ~65%,  nontransparent ~88%
    # (nontransparent means Alpha > 0)
    "default": {
        "ink_low":                          2.5,
        "ink_high":                        12.0,
        "alpha_strength":                   1.10,
        "alpha_clamp_max":                  255,
        "paper_percentile_lo":              65.0,
        "paper_percentile_hi":              97.0,
        "paper_max_chroma":                 10.0,
        "local_bg_sigma_ratio":             0.05,
        "local_bg_enabled":                 True,
        "local_bg_gain":                    0.70,
        "weight_L":                         1.0,
        "weight_a":                         2.2,
        "weight_b":                         2.2,
        "saturation_boost":                 0.50,
        "darkness_boost":                   0.60,
        "local_contrast_enabled":           True,
        "local_contrast_ksize":             9,
        "local_contrast_strength":          0.30,
        "noise_min_area":                   0,
        "noise_median_ksize":               0,
        "auto_crop":                        True,
        "auto_crop_alpha_threshold":        12,
        "auto_crop_border":                 2,
        "save_debug_images":                True,
        "desaturate_paper_tint":            False,
    },

    # --------------------------- conservative ------------------------------
    # Cleaner, less faint haze kept. Drops the weakest near-paper pixels. Use
    # when preserve_light introduces too much semi-transparent stain around
    # edges.  noise_min_area raised to 2 to kill single isolated specks only.
    "conservative": {
        "ink_low":                          3.5,
        "ink_high":                        14.0,
        "alpha_strength":                   1.00,
        "alpha_clamp_max":                  255,
        "paper_percentile_lo":              65.0,
        "paper_percentile_hi":              97.0,
        "paper_max_chroma":                 10.0,
        "local_bg_sigma_ratio":             0.05,
        "local_bg_enabled":                 True,
        "local_bg_gain":                    0.70,
        "weight_L":                         1.0,
        "weight_a":                         2.2,
        "weight_b":                         2.2,
        "saturation_boost":                 0.50,
        "darkness_boost":                   0.60,
        "local_contrast_enabled":           True,
        "local_contrast_ksize":             9,
        "local_contrast_strength":          0.15,
        "noise_min_area":                   2,
        "noise_median_ksize":               0,
        "auto_crop":                        True,
        "auto_crop_alpha_threshold":        12,
        "auto_crop_border":                 2,
        "save_debug_images":                True,
        "desaturate_paper_tint":            False,
    },

    # ------------------------ preserve_light_ink ---------------------------
    # Maximise faint-ink recall at the cost of some residual semi-transparent
    # halo. Use as the first stop for "stamps with lots of missing ink / wear".
    # raise alpha_strength to pull mid-range ink pixels up in opacity.
    "preserve_light": {
        "ink_low":                          1.5,
        "ink_high":                         9.0,
        "alpha_strength":                   1.20,
        "alpha_clamp_max":                  255,
        "paper_percentile_lo":              65.0,
        "paper_percentile_hi":              97.0,
        "paper_max_chroma":                 10.0,
        "local_bg_sigma_ratio":             0.05,
        "local_bg_enabled":                 True,
        "local_bg_gain":                    0.70,
        "weight_L":                         1.0,
        "weight_a":                         2.2,
        "weight_b":                         2.2,
        "saturation_boost":                 0.50,
        "darkness_boost":                   0.60,
        "local_contrast_enabled":           True,
        "local_contrast_ksize":             9,
        "local_contrast_strength":          0.45,
        "noise_min_area":                   0,
        "noise_median_ksize":               0,
        "auto_crop":                        True,
        "auto_crop_alpha_threshold":        12,
        "auto_crop_border":                 2,
        "save_debug_images":                True,
        "desaturate_paper_tint":            False,
    },
}


# Processing order (processor.py extract_array). IMPORTANT for rollback: the
# order of local-luminance and paper-estimate matters because of Lab-space
# consistency.  In V1 the order is LOCAL CORRECTION FIRST, then PAPER ESTIMATE
# from the corrected Lab float. Earlier versions did it the other way around
# and produced effectively-always-opaque results (do not revert that ordering).
V1_PIPELINE_STEPS = [
    "0. locate_stamp_subregion_bbox on rgb_uint8 -> crop working region.",
    "1. rgb_uint8 -> Lab float (real perceptual, not cv2 packed uint8).",
    "2. local luminance correction on L channel only, gain=0.70, sigma_ratio=5%.",
    "3. paper model estimate from lab_norm (multi-point percentile + chroma<=10, 2-pass 5*MAD outlier clip, with fallbacks).",
    "4. fused_ink_score = weighted Lab distance * chroma-ratio boost * darkness boost * local-contrast boost (clamped multipliers to avoid exploding).",
    "5. score_to_alpha via smoothstep(ink_low, ink_high) then pow(alpha_strength) clamp [0,255].",
    "6. very_light_denoise: only min-area connected-component drop (default OFF) + optional 3x3 median (default OFF).",
    "7. optional auto_crop: bbox on alpha>12, border +2, to real ink (never to image edge).",
    "8. RGB is copied verbatim from working_rgb inside crop; alpha is dstacked unchanged.",
    "9. Debug images saved alongside (01..05b, 02b, 03b..03c, 04..04b, 05b).",
]


def apply_v1_preset(name: str, cfg):
    """Helper: mutate a live ExtractorConfig instance back to V1 values for `name`."""
    params = V1_CONFIG_PRESETS[name]
    for k, v in params.items():
        setattr(cfg, k, v)
    return cfg
