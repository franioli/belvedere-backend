import boto3
from botocore.client import Config
from django.conf import settings


def build_s3_client():
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


def get_object_bytes(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read(), response.get("ContentType")
