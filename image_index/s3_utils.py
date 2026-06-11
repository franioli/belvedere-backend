import boto3
from botocore.client import BaseClient, Config
from django.conf import settings


def build_s3_client() -> BaseClient:
    """Build and return a configured S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION_NAME,
        config=Config(
            signature_version="s3v4",
            s3={
                "addressing_style": "virtual",
                "payload_signing_enabled": False,
            },
        ),
    )


def get_object_bytes(s3: BaseClient, bucket: str, key: str) -> tuple[bytes, str | None]:
    """Fetch an object from S3 and return its bytes and content type."""
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read(), response.get("ContentType")


def put_object_bytes(
    s3: BaseClient, bucket: str, key: str, data: bytes, content_type: str
) -> None:
    """Store bytes in S3 with the given content type."""
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def generate_presigned_url(
    s3: BaseClient, bucket: str, key: str, expires_in: int = 3600
) -> str:
    """Return a presigned GET URL for an S3 object, valid for expires_in seconds."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
