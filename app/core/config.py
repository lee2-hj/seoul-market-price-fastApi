from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "backend_fastApi"
    debug: bool = False

    # mart 조회 조건(WHERE) 매칭 데이터가 없을 때 과거 base_date 파티션으로 소급 조회할
    # 최대 파티션 개수. 배치가 매일 1회 적재된다고 가정하면 30 ≈ 최근 30일 소급.
    max_base_date_lookback: int = Field(
        default=30,
        description="Maximum number of partitions to look back when searching for matching data",
    )

    # 프론트엔드 CORS 허용 origin (dev 기본값: 전체 허용)
    cors_origins: list[str] = ["*"]

    # MinIO / S3 접속 정보
    s3_end_point: str
    s3_access_key: str
    s3_secret_key: str
    s3_use_ssl: bool = False
    s3_url_style: str = "path"
    aws_region: str = "ap-northeast-2"

    # 데이터 레이크 버킷
    raw: str = "lake"
    lake: str = "warehouse"


settings = Settings()
