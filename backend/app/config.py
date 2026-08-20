"""应用配置：基于 pydantic-settings，从环境变量/.env 读取。

路径锚定到项目根目录（backend/ 的上一级），保证 .env 与 data/ 位置不受运行目录影响。
"""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → app → backend → 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置，字段对应 .env 中的键（不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "电子集章本"
    debug: bool = False

    # 数据库
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'cyber_stamping.db'}"

    # 存储路径（相对项目根；ensure_dirs 会锚定到 PROJECT_ROOT）
    data_dir: str = "data"
    stamps_dir: str = "data/stamps"
    original_dir: str = "data/stamps/original"
    sticker_dir: str = "data/stamps/sticker"

    # 认证
    secret_key: str = "change_me_in_production_please_use_a_long_random_string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 默认 7 天

    # 单密码登录账号
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # 高德 Web 服务 API（P2 启用）
    amap_key: str = ""

    # rembg 抠图模型：u2netp(~4.7MB,快速) / u2net(~176MB,高质量) / silueta(~43MB)
    rembg_model: str = "u2netp"

    # 跨域（开发期放行前端 dev server）
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def _resolve(self, p: str) -> Path:
        """把相对路径锚定到项目根；绝对路径原样返回。"""
        path = Path(p)
        return path if path.is_absolute() else (PROJECT_ROOT / path)

    def ensure_dirs(self) -> None:
        """启动时确保所有存储目录存在。"""
        for path in (self.data_dir, self.stamps_dir, self.original_dir, self.sticker_dir):
            self._resolve(path).mkdir(parents=True, exist_ok=True)

    def abs_data_dir(self) -> Path:
        return self._resolve(self.data_dir)


settings = Settings()
