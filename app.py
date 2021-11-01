import io
import logging
import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from PIL import Image

import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
dynamodb = boto3.client('dynamodb')

environment = os.environ.get("APP_ENV")

envDict = {
    "production": config,
}
settings = envDict[environment]


class DynamoDBError(ClientError):
    pass


def resize_image_photo_reservation(
        image_size: tuple, key: str, bucket: str
) -> None:
    """
        Generates image thumbnail 
        :rtype: object
        :param s3_response: The get_object S3 response
    """
    #  Curiously S3 get_object call must be in the same execution context 
    #  of StreamBody (object comming from S3) for it to be converted into 
    #  BufferReader properly inside the lambda. 
    try:
        s3_response = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as err:
        logger.error(f"Original reservation profile  file not exists in S3 {key}")
        raise

    content_type = s3_response.get("ContentType")
    file_extension = get_file_extension(content_type).upper()
    memfile = io.BytesIO()
    format = "JPEG" if file_extension == "JPG" else file_extension

    try:
        with Image.open(io.BufferedReader(s3_response["Body"]._raw_stream)) as image:
            image.thumbnail(image_size)
            image.save(memfile, format=format)
            return memfile.getvalue(), format.lower()
    except Exception as err:
        logger.error("Pillow error trying to resize the image")
        raise err


def generate_reservation(bucket: str, user_id: int,
                   reservation_uuid: str, type_: str, key: str) -> str:
    """
        Resize image to thumbnail or mobile and uploads
        the new images into S3
        
        :type bucket: object
        :returns S3 key of the thumbnail
    """

    if type_ == "client_1":
        reservation_key = f"{user_id}/{type_}/{reservation_uuid}"
        resize_image_photo_reservation(
            image_size=settings.RESERVATION_STATUS_NUMBERS,
            bucket=bucket,
            key=key)
        s3.put_object(Bucket=bucket,
                      Key=reservation_key,
                      ContentType=f"application/{format}",
                      CacheControl="no-cache")
        return reservation_key

    elif type_ == "client_2":
        reservation_client_key = f"{user_id}/{type_}/{reservation_uuid}"
        resize_image_photo_reservation(
            image_size=settings.RESERVATION_CLIENT_STATUS_NUMBERS,
            bucket=bucket,
            key=key)
        s3.put_object(Bucket=bucket,
                      Key=reservation_client_key,
                      ContentType=f"application/{format}",
                      CacheControl="no-cache")

        return reservation_client_key
    else:
        logger.error(f"Invalid file type generation {type_}, type allowed ")
        raise Exception(f"Invalid file type generation {type_}, "
                        f"only mobile and thumbnail allowed")


def get_file_extension(content_type: str = None) -> str:
    """
        Get the file extension of the photo 
        :param metadata: The ContentType parameter of the item comming from S3

    """

    if content_type:
        file_extension = content_type.split("/")[-1]
        if file_extension.strip() in ["jpg", "jpeg", "png"]:
            return file_extension
        else:
            raise Exception("Invalid file extension %s" % file_extension)
    else:
        raise Exception("Unable to fetch the file extension")


def update_dynamo_create_reservation(user_id: str, thumbnail_url: str,
                                mobile_high_quality_url: str, sort_key: str) -> None:
    """
        Updates mobile high quality and thumbnail urls in dynamo photo info table
        :raises DynamoDBError: If ClientError is raised when performing the update
    """

    try:
        response = dynamodb.update_item(
            TableName=settings.PHOTO_GALLERY_TABLE,
            Key={
                "user_id": {
                    "S": user_id
                },
                "sort_key": {
                    "S": sort_key
                }
            },
            UpdateExpression=
            "SET photo_info.mobile_thumbnail_url = :mobile_thumbnail_url, " \
            "photo_info.mobile_high_quality_url = :mobile_high_quality_url",
            ExpressionAttributeValues={
                ":mobile_thumbnail_url": {"S": thumbnail_url},
                ":mobile_high_quality_url": {"S": mobile_high_quality_url}
            },
            ReturnValues="UPDATED_NEW")
    except DynamoDBError:
        raise
    else:
        logger.info(
            f"Photo original, thumbnail and mobile high quality, "
            f"ubdated successfully for photo {response}")


def get_dynamo_insert_record(event: dict):
    """
        Filters only the INSERT events from dynamoDB stream
        that means lambda is going to be triggered only when 
        new item is created.
    """

    for record in event.get("Records"):
        event_name = record["eventName"]
        logger.info(f"Event name: {event_name}")
        if event_name == "INSERT":
            user_id = record["dynamodb"]["Keys"]["user_id"]["S"]
            photo_uuid = record["dynamodb"]["NewImage"]["photo_uuid"]["S"]
            sort_key = record["dynamodb"]["NewImage"]["sort_key"]["S"]
            s3_key = f"{user_id}/original/{photo_uuid}"
            yield user_id, photo_uuid, s3_key, sort_key


def lambda_handler(event, context) -> None:
    """
        Photo gallery lambda function:
        1. Downloads original file and stores in the buffer
        2. Generate thumbnail and mobile HQI (Hight Quality Image)
          2.2 Resizes image using binary form
          2.3 Puts new file in S3 bucket
        3. Generates Clooudfront urls 
        4. Update DynamoDB table with thumbnail, mobile and original urls

        :param event: DynamoDB stream event 
        :param context:
        :return:
    """

    for user_id, photo_uuid, s3_key, sort_key in get_dynamo_insert_record(event):
        logger.info(f"Processing user_id: {user_id}, photo_uuid: {photo_uuid},"
                    f" s3_key: {s3_key}, dynamo_key: {sort_key}")
        try:
            thumbnail_key = generate_reservation(
                bucket=settings.PHOTO_GALLERY_S3_BUCKET,
                user_id=user_id,
                photo_uuid=photo_uuid,
                type_='thumbnail',
                key=s3_key)
            mobile_high_quality_key = generate_reservation(
                bucket=settings.PHOTO_GALLERY_S3_BUCKET,
                user_id=user_id,
                photo_uuid=photo_uuid,
                type_='mobile',
                key=s3_key)

            thumbnail_url = f"{settings.BASE_CLOUDFRONT_URL}/{thumbnail_key}"
            mobile_high_quality_url = f"{settings.BASE_CLOUDFRONT_URL}/{mobile_high_quality_key}"
            update_dynamo_create_reservation(
                user_id=user_id,
                sort_key=sort_key,
                thumbnail_url=thumbnail_url,
                mobile_high_quality_url=mobile_high_quality_url)

        except DynamoDBError as err:
            logger.error(f"Error trying to connect with DynamoDB: {str(err)}")
        except ClientError as err:
            logger.error(f"Error trying to connect with S3: {str(err)}")
        except Exception as err:
            logger.error(f"Unknown exception: {str(err)}")
        else:
            logger.info(f"Lambda processed successfully photo: {s3_key}")
