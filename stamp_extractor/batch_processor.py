"""
stamp_extractor.batch_processor
===============================
批量处理入口。两种方式：
    1) 单张图片 → 单张输出 + 单张 debug 目录
    2) 整个文件夹（可递归）→ 保持相对目录映射
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from .config import ExtractorConfig
from .processor import StampExtractor, ExtractResult
from .utils import list_images, short_stem


def process_batch(
    input_paths: Iterable[Path],
    output_dir: Path,
    debug_dir: Optional[Path] = None,
    cfg: Optional[ExtractorConfig] = None,
    verbose: bool = True,
) -> List[ExtractResult]:
    """
    批量处理。每张图输出：
        output_dir/{原文件名（改png）}
        debug_dir/{原文件名 stem}/01~05.*  （如果 save_debug_images=True 且 debug_dir 给了）
    """
    cfg = cfg or ExtractorConfig.defaults()
    ext = StampExtractor(cfg)
    results: List[ExtractResult] = []
    input_paths = list(input_paths)
    total = len(input_paths)

    for i, src in enumerate(input_paths, 1):
        stem = short_stem(src)
        safe_stem = stem or src.stem
        out_path = Path(output_dir) / f"{safe_stem}.png"
        per_debug = None
        if cfg.save_debug_images and debug_dir is not None:
            per_debug = Path(debug_dir) / safe_stem
            per_debug.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        if verbose:
            print(f"\n[{i}/{total}] {src.name}  →  {out_path.name}")
        try:
            res = ext.extract_file(src, out_path, debug_dir=per_debug)
        except Exception as e:
            print(f"  ❌ 失败: {e!r}", file=sys.stderr)
            raise
        dt = time.time() - t0
        if verbose:
            st = res.stats
            print(f"  ✅ {dt:.1f}s  shape={st['shape']}  opaque={st['opaque_pct']:.2f}%  "
                  f"nontransparent={st['nontransparent_pct']:.2f}%")
        results.append(res)

        # 写一个统计 JSON（一张一个，和 debug 目录并列）
        if per_debug is not None:
            stats_json = dict(
                source=str(src),
                output=str(out_path),
                seconds=round(dt, 2),
                stats=res.stats,
                paper={
                    "n_samples": res.paper.n_samples,
                    "lab_mean": [float(x) for x in res.paper.lab_mean.tolist()],
                    "lab_std": [float(x) for x in res.paper.lab_std.tolist()],
                },
                config=str(cfg),
            )
            (per_debug / "stats.json").write_text(
                json.dumps(stats_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    return results
