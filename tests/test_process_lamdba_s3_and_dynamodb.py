import boto3
import datetime
import requests
import unittest
import uuid

from botocore.client import Config
from boto3.dynamodb.conditions import Key
from config import Development
from tenacity import retry, stop_after_attempt, stop_after_delay

s3 = boto3.client('s3', config=Config(signature_version='s3v4'))
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
settings = Development

DEFAULT_DELAY = 5
DEFAULT_RETRY_AMOUNT = 5


class RetryExhaustionError(Exception):
    pass


@retry(stop=(stop_after_delay(DEFAULT_DELAY) & stop_after_attempt(
    DEFAULT_RETRY_AMOUNT)))
def retry_checking_if_lambda_worked(table, user_id, sort_key):
    """
    This tenacity function queries DDB with 5 attempts and 5 seconds delay
    in case it does not work, with the objective to get 2 fields
    'reservation_photo_url' and 'mobile_thumbnail_urlreservation_client_photo_url'.
    If both fields are not None, so lambda is working correctly.

    :param sort_key:type:(string): combination from user with the uuid,
                                    user id and date created
    :param  user_id:type:(int): the user id
    :param  table:type:(object): the DDB table object
    :raise: Error in lambda function
    :return: new_response_ddb:type:(object): DDB query response
    """
    new_response_ddb = table.query(
        KeyConditionExpression=
        Key('user_id').eq(str(user_id)) & Key('sort_key').eq(str(sort_key)))
    item = new_response_ddb['Items'][0]

    # If the field 'reservation_photo_url' or 'reservation_client_photo_url' are
    # None, so lambda is not working

    if not item:
        raise RetryExhaustionError('Still no item url after 5 retries, '
                                   'please check lambda function')
    return new_response_ddb


def get_dynamodb_response(table, user_id, sort_key):
    """
    Get the response from DDB verifying if lambda function works correctly

    :param sort_key:type:(string): combination from user with the uuid,
                                    user id and date created
    :param  user_id:type:(int): the user id
    :param  table:type:(object): the DDB table object
    :return response: DDB query
    """
    response = retry_checking_if_lambda_worked(table, user_id, sort_key)
    return response


class TestGeneralLambdaHandler(unittest.TestCase):

    def setUp(self):

        self.user_id = 4
        self.uuid = str(uuid.uuid4())
        self.current_time = str(datetime.datetime.utcnow())
        self.sort_key = "{date_created}#1#{uuid}".format(
            date_created=self.current_time, uuid=self.uuid)
        with open('tests/utils/image_test.png', 'rb') as f:
            self.image = f.read()
            if '.png' in f.name:
                self.headers_image = {'Content-Type': 'image/png'}
            elif ".jpg" in f.name or ".jpeg" in f.name:
                self.headers_image = {'Content-Type': 'image/jpeg'}
            else:
                raise Exception("Invalid file type")

        presigned_url_params = {
            "Bucket": "RESERVATION_REVIFAST",
            "Key": "{}/original/{}".format(str(self.user_id), self.uuid)
        }
        self.url = s3.generate_presigned_url(
            'put_object', Params=presigned_url_params,
            ExpiresIn=3600, HttpMethod='PUT'
        )

    def test_lambda_procesed_dynamo_event(self):
        """
        Should check the files are in S3 and the news urls are in the fields:
        'reservation_photo_url'm and 'reservation_client_photo_url'
        """

        r = requests.put(self.url, data=self.image,
                         headers=self.headers_image)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'')
        table = dynamodb.Table("RESERVATION_REVIFAST_TABLE")

        response_ddb = table.put_item(
            Item={
                "date_created": self.current_time,
                "date_updated": None,
                "photo_info": {
                    "caption": "animal crossing",
                    "reservation_photo_url": None,
                    "reservation_client_photo_url": None,
                    "original_url": "{}/{}/original/{}".format(
                        "RESERVATION_REVIFAST",
                        str(self.user_id),
                        self.uuid)
                },
                "photo_uuid": self.uuid,
                "sort_key": "{}".format(self.sort_key),
                "status": "ACTIVE",
                "upload_reversed_order": 1,
                "user_id": "{}".format(str(self.user_id))
            }
        )

        self.assertEqual(response_ddb['ResponseMetadata']['HTTPStatusCode'],
                         200)
        self.assertEqual(response_ddb['ResponseMetadata']['RetryAttempts'], 0)

        # Get the response from DDB
        new_response_ddb = get_dynamodb_response(table, self.user_id,
                                                 self.sort_key)

        item = new_response_ddb['Items'][0]

        reservation_photo_url = item['photo_info']['reservation_photo_url']
        reservation_client_photo_url = item['photo_info'][
            'reservation_client_photo_url']

        self.assertTrue(reservation_photo_url)
        self.assertTrue(reservation_client_photo_url)
        self.assertEqual(reservation_photo_url.split("/")[3], str(self.user_id))
        self.assertEqual(reservation_client_photo_url.split("/")[3],
                         str(self.user_id))
        self.assertEqual(reservation_photo_url.split("/")[5], self.uuid)
        self.assertEqual(reservation_client_photo_url.split("/")[5], self.uuid)

    def test_lambda_process_with_bad_uuid(self):
        """
        Should throw an exception because of the different uuid
        """
        bad_uuid = 'fdcca17e-898a-4f98-9969-9ea57a1bb123'

        r = requests.put(self.url, data=self.image,
                         headers=self.headers_image)

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'')
        table = dynamodb.Table("RESERVATION_REVIFAST_TABLE")

        response_ddb = table.put_item(
            Item={
                "date_created": self.current_time,
                "date_updated": None,
                "photo_info": {
                    "caption": "animal crossing",
                    "reservation_photo_url": None,
                    "reservation_client_photo_url": None,
                    "original_url": "{}/{}/original/{}".format(
                        "RESERVATION_REVIFAST",
                        str(self.user_id),
                        bad_uuid)
                },
                "photo_uuid": self.uuid,
                "sort_key": "{}".format(self.sort_key),
                "status": "ACTIVE",
                "upload_reversed_order": 1,
                "user_id": "{}".format(str(self.user_id))
            }
        )

        self.assertEqual(response_ddb['ResponseMetadata']['HTTPStatusCode'],
                         200)
        self.assertEqual(response_ddb['ResponseMetadata']['RetryAttempts'], 0)

        # Get the response from DDB
        new_response_ddb = get_dynamodb_response(table, self.user_id,
                                                 self.sort_key)

        item = new_response_ddb['Items'][0]

        reservation_photo_url = item['photo_info']['reservation_photo_url']
        reservation_client_photo_url = item['photo_info'][
            'reservation_client_photo_url']

        self.assertTrue(reservation_photo_url)
        self.assertTrue(reservation_client_photo_url)
        self.assertEqual(reservation_photo_url.split("/")[3], str(self.user_id))
        self.assertEqual(reservation_client_photo_url.split("/")[3],
                         str(self.user_id))
        self.assertNotEqual(reservation_photo_url.split("/")[5], bad_uuid)
        self.assertNotEqual(reservation_client_photo_url.split("/")[5],
                            bad_uuid)
