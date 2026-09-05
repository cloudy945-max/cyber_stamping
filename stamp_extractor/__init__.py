"""
stamp_extractor.__init__
包 init，方便从外部 `from stamp_extractor import StampExtractor, ExtractorConfig`。
"""
from .config import ExtractorConfig
from .processor import StampExtractor, ExtractResult
from .batch_processor import process_batch

__all__ = [
    "ExtractorConfig",
    "StampExtractor",
    "ExtractResult",
    "process_batch",
]
