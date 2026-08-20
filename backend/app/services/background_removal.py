"""背景去除：rembg AI 抠图，生成透明背景贴纸。

设计要点：
- 模型延迟加载（首次处理时载入，之后常驻内存，避免每次请求重复加载）
- 模型文件缺失时直接返回 None，不触发下载（避免 GitHub 访问超时阻断上传请求）
- 模型不可用/网络异常时返回 None，原图仍可访问（process_status=failed）
- pymatting 桩注入：rembg 在 bg.py 顶层 import pymatting，触发 numba @njit(parallel=True)
  急编译，在国内 Windows 环境下首次 import 会卡死数分钟。pymatting 仅在 alpha_matting=True
  时被调用（我们用不到），所以在 import rembg 之前把 pymatting 的相关子模块替换为桩模块。

模型部署说明：
- 默认使用 u2netp（~4.7MB，下载快），可在 .env 中通过 REMBG_MODEL 切换为
  u2net（~176MB，质量更高）或 silueta（~43MB，速度/质量折中）
- rembg 默认从 GitHub releases 下载，国内网络可能超时，建议预先下载对应 .onnx
  并放置到 U2NET_HOME（默认 ~/.u2net/），或设置环境变量 U2NET_HOME 指向已放模型的目录
- 模型文件存在后，本服务会自动加载使用
"""
import logging
import os
import sys
import types
from pathlib import Path
from typing import Optional

from PIL import Image

from ..config import settings

logger = logging.getLogger(__name__)


def _stub_pymatting() -> None:
    """在 import rembg 之前注入 pymatting 桩模块，避免 numba 急编译卡死。

    rembg/bg.py 顶层导入：
        from pymatting.alpha.estimate_alpha_cf import estimate_alpha_cf
        from pymatting.foreground.estimate_foreground_ml import estimate_foreground_ml
        from pymatting.util.util import stack_images
    仅在 alpha_matting=True 时调用，我们用不到 → 桩化即可。
    """
    if "pymatting.alpha.estimate_alpha_cf" in sys.modules:
        return  # 已加载真模块，不要覆盖
    stubs = {
        "pymatting": types.ModuleType("pymatting"),
        "pymatting.alpha": types.ModuleType("pymatting.alpha"),
        "pymatting.alpha.estimate_alpha_cf": types.ModuleType("pymatting.alpha.estimate_alpha_cf"),
        "pymatting.foreground": types.ModuleType("pymatting.foreground"),
        "pymatting.foreground.estimate_foreground_ml": types.ModuleType(
            "pymatting.foreground.estimate_foreground_ml"
        ),
        "pymatting.util": types.ModuleType("pymatting.util"),
        "pymatting.util.util": types.ModuleType("pymatting.util.util"),
    }
    # 设置 __path__ 让 Python 把它们当成 package（防止后续 import 子模块时再去找真实文件）
    for name, mod in stubs.items():
        if "." in name:
            mod.__path__ = []  # type: ignore[attr-defined]
    # 给 rembg/bg.py 用到的名字占位
    stubs["pymatting.alpha.estimate_alpha_cf"].estimate_alpha_cf = lambda *a, **kw: None  # type: ignore[attr-defined]
    stubs["pymatting.foreground.estimate_foreground_ml"].estimate_foreground_ml = lambda *a, **kw: None  # type: ignore[attr-defined]
    stubs["pymatting.util.util"].stack_images = lambda *a, **kw: None  # type: ignore[attr-defined]
    # 设置包关系，避免 import 机制去找真包
    stubs["pymatting"].alpha = stubs["pymatting.alpha"]  # type: ignore[attr-defined]
    stubs["pymatting"].foreground = stubs["pymatting.foreground"]  # type: ignore[attr-defined]
    stubs["pymatting"].util = stubs["pymatting.util"]  # type: ignore[attr-defined]
    stubs["pymatting.alpha"].estimate_alpha_cf = stubs["pymatting.alpha.estimate_alpha_cf"]  # type: ignore[attr-defined]
    stubs["pymatting.foreground"].estimate_foreground_ml = stubs["pymatting.foreground.estimate_foreground_ml"]  # type: ignore[attr-defined]
    stubs["pymatting.util"].util = stubs["pymatting.util.util"]  # type: ignore[attr-defined]
    for name, mod in stubs.items():
        sys.modules.setdefault(name, mod)

# 延迟加载的模型 session（进程级常驻）
_session = None
_session_model: Optional[str] = None  # 记录当前 session 使用的模型名
# 模型缺失标志，避免每次请求都重新检查文件
_no_model_models: set = set()


def _u2net_home() -> Path:
    """获取 U2NET_HOME 目录（与 rembg/base.py 一致）。"""
    home = os.getenv("U2NET_HOME") or os.path.join(
        os.getenv("XDG_DATA_HOME", os.path.expanduser("~")), ".u2net"
    )
    return Path(home)


def _model_name() -> str:
    """当前配置的模型名（来自 settings.rembg_model）。"""
    return settings.rembg_model or "u2netp"


def _model_file_exists(model: str) -> bool:
    """检查指定模型的 .onnx 是否已就位。"""
    return (_u2net_home() / f"{model}.onnx").exists()


def _get_session():
    """延迟加载 rembg session。模型文件缺失则跳过，返回 None。

    若配置切换了模型名，会重新加载新模型（缓存旧的不再使用）。
    """
    global _session, _session_model
    model = _model_name()

    # 配置变更 → 丢弃旧 session，重新加载
    if _session is not None and _session_model != model:
        logger.info("rembg model switched: %s -> %s, reloading...", _session_model, model)
        _session = None
        _session_model = None

    if _session is not None:
        return _session
    if model in _no_model_models:
        return None

    if not _model_file_exists(model):
        logger.warning(
            "%s model not found at %s/%s.onnx, skip background removal. "
            "Please download from "
            "https://github.com/danielgatis/rembg/releases/download/v0.0.0/%s.onnx",
            model,
            _u2net_home(),
            model,
            model,
        )
        _no_model_models.add(model)
        return None

    try:
        _stub_pymatting()
        from rembg import new_session

        logger.info("Loading rembg session (model=%s)...", model)
        _session = new_session(model)
        _session_model = model
        logger.info("rembg session loaded.")
        return _session
    except Exception as e:
        logger.warning("rembg session load failed: %s", e)
        _session = None
        return None


def remove_background(src_path: Path, dst_path: Path) -> Optional[Path]:
    """抠图：输入图片 → 输出透明背景 PNG。

    Args:
        src_path: 输入图片（增强后的 enhanced.png）
        dst_path: 抠图后保存路径（PNG，保留 alpha 通道）

    Returns:
        dst_path（成功）/ None（rembg 不可用或处理失败，调用方降级用原图）
    """
    try:
        _stub_pymatting()
        from rembg import remove
    except ImportError as e:
        logger.warning("rembg not installed: %s", e)
        return None

    session = _get_session()
    if session is None:
        return None

    try:
        with Image.open(src_path) as img:
            # rembg 直接接收 PIL Image，输出带 alpha 的 PIL Image
            out_img = remove(img, session=session)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            out_img.save(dst_path, "PNG")
            return dst_path
    except Exception as e:
        logger.warning("remove_background failed for %s: %s", src_path, e)
        return None
