import boto3

from botocore.config import Config

from api.config import Settings

class S3Connection:
    def __init__(self, **kwargs):
        self.env_settings = Settings()
        self.s3 = boto3.client('s3',
                               endpoint_url=self.env_settings.ENDPOINT,
                               aws_access_key_id=self.env_settings.S3_KEY_ID,
                               aws_secret_access_key=self.env_settings.S3_SECRET,
                               region_name=self.env_settings.S3_REGION,
                               config=Config(signature_version='s3v4'))

        expires_in = kwargs.pop('expires_in', None)
        if expires_in is not None:
            self.expires_in = expires_in

    def get_presigned_url(self, params={'Bucket': '', 'Key': ''}, url_method='get_object', expires_in=60):
        return self.s3.generate_presigned_url(url_method, Params=params, ExpiresIn=expires_in)