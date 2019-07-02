import unittest
import target_stitch
from target_stitch import StitchHandler, TargetStitchException, DEFAULT_STITCH_URL, ourSession, finish_requests
import io
import os
import json
import asyncio
try:
    from tests.gate_mocks import mock_in_order_all_200, mock_out_of_order_all_200, mock_in_order_first_errors, mock_in_order_second_errors, mock_out_of_order_first_errors, mock_out_of_order_second_errors
except ImportError:
    from gate_mocks  import mock_in_order_all_200, mock_out_of_order_all_200, mock_in_order_first_errors, mock_in_order_second_errors, mock_out_of_order_first_errors, mock_out_of_order_second_errors

def load_sample_lines(filename):
    with open('tests/' + filename) as fp:
        return [line for line in fp]

def token():
    token = os.getenv('TARGET_STITCH_TEST_TOKEN')
    if not token:
        raise Exception('Integration tests require TARGET_STITCH_TEST_TOKEN environment variable to be set')
    return token

class TestRecordWithNullKeyProperty(unittest.TestCase):
    def setUp(self):
        handler = StitchHandler(token(),
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                target_stitch.DEFAULT_MAX_BATCH_RECORDS)
        out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], out, 4000000, 20000, 100000)

    def test(self):
        queue = load_sample_lines('record_missing_key_property.json')
        pattern = ('Error persisting data for table '
                   '"test_record_missing_key_property": '
                   'Record is missing key property id')
        with self.assertRaisesRegex(TargetStitchException, pattern):
            self.target_stitch.consume(queue)

class TestNoToken(unittest.TestCase):

    def setUp(self):
        token = None
        handler = StitchHandler(token,
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                target_stitch.DEFAULT_MAX_BATCH_RECORDS)
        out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], out, 4000000, 20000, 100000)

    def test(self):
        queue = load_sample_lines('record_missing_key_property.json')
        pattern = 'Not Authorized'
        with self.assertRaisesRegex(TargetStitchException, pattern):
            self.target_stitch.consume(queue)


class FakePost:
    def __init__(self, requests_sent, makeFakeResponse):
        self.requests_sent = requests_sent
        self.makeFakeResponse = makeFakeResponse

    async def __aenter__(self):
        return self.makeFakeResponse(self.requests_sent)

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(1)

class FakeSession:
    def __init__(self, makeFakeResponse):
        self.requests_sent = 0
        self.makeFakeResponse = makeFakeResponse

    def post(self, url, *, data, **kwargs):
        self.requests_sent = self.requests_sent + 1
        return FakePost(self.requests_sent, self.makeFakeResponse)


class AsyncPushToGate(unittest.TestCase):
    def setUp(self):
        token = None
        handler = StitchHandler(token,
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                2)
        self.out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], self.out, 4000000, 2, 100000)
        self.queue = [json.dumps({"type": "SCHEMA", "stream": "chicken_stream",
                                  "key_properties": ["id"],
                                  "schema": {"type": "object",
                                             "properties": {"id": {"type": "integer"},
                                                            "name": {"type": "string"}}}})]


    # 2 requests
    # both with state
    # in order responses
    def test_requests_in_order(self):
        target_stitch.ourSession = FakeSession(mock_in_order_all_200)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        finish_requests()

        emitted_state = list(map(json.loads, self.out.getvalue().strip().split('\n')))
        self.assertEqual(len(emitted_state), 2)
        self.assertEqual( emitted_state[0], {'bookmarks': {'chicken_stream': {'id': 1}}})
        self.assertEqual( emitted_state[1], {'bookmarks': {'chicken_stream': {'id': 3}}})


    # 2 requests
    # last SENT request has state
    # in order
    def test_requests_in_order_first_has_no_state(self):
        target_stitch.ourSession = FakeSession(mock_in_order_all_200)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        finish_requests()

        emitted_state = list(map(json.loads, self.out.getvalue().strip().split('\n')))
        self.assertEqual(len(emitted_state), 1)
        self.assertEqual( emitted_state[0], {'bookmarks': {'chicken_stream': {'id': 3}}})

    # 2 requests
    # both with state.
    # out of order responses
    def test_requests_out_of_order(self):
        target_stitch.ourSession = FakeSession(mock_out_of_order_all_200)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records

        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        finish_requests()

        emitted_state = list(map(json.loads, self.out.getvalue().strip().split('\n')))
        self.assertEqual(len(emitted_state), 2)
        self.assertEqual( emitted_state[0], {'bookmarks': {'chicken_stream': {'id': 1}}})
        self.assertEqual( emitted_state[1], {'bookmarks': {'chicken_stream': {'id': 3}}})

    # 2 requests.
    # both with state.
    # in order
    # first request errors
    def test_requests_in_order_first_errors(self):
        target_stitch.ourSession = FakeSession(mock_in_order_first_errors)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        our_exception = None
        try:
            finish_requests()
        except Exception as ex:
            our_exception = ex

        self.assertIsNotNone(our_exception)
        self.assertTrue(isinstance(our_exception, TargetStitchException))

        #no state is emitted
        emitted_state = self.assertEqual(self.out.getvalue(), '')

    # 2 requests.
    # both with state.
    # in order
    # second SENT request errors
    def test_requests_in_order_second_errors(self):
        target_stitch.ourSession = FakeSession(mock_in_order_second_errors)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        our_exception = None
        try:
            finish_requests()
        except Exception as ex:
            our_exception = ex

        self.assertIsNotNone(our_exception)
        self.assertTrue(isinstance(our_exception, TargetStitchException))

        emitted_state = self.out.getvalue().strip().split('\n')
        self.assertEqual(1, len(emitted_state))
        self.assertEqual({'bookmarks': {'chicken_stream': {'id': 1}}}, json.loads(emitted_state[0]))

    # 2 requests.
    # both with state.
    # out of order
    # first SENT request errors
    def test_requests_out_of_order_first_errors(self):
        target_stitch.ourSession = FakeSession(mock_out_of_order_first_errors)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        our_exception = None
        try:
            finish_requests()
        except Exception as ex:
            our_exception = ex

        self.assertIsNotNone(our_exception)
        self.assertTrue(isinstance(our_exception, TargetStitchException))

        #no state is emitted
        self.assertEqual(self.out.getvalue(), '')

    # 2 requests.
    # both with state.
    # out of order
    # second SENT request errors
    def out_of_order_second_errors(self, requests_sent):
        class FakeResponse:
            def __init__(self, requests_sent):
                self.requests_sent = requests_sent

            async def json(self):
                if (self.requests_sent == 1):
                    self.status = 200
                    await asyncio.sleep(3)
                    return {"status" : "finished request {}".format(requests_sent)}

                self.status = 400
                return {"status" : "finished request {}".format(requests_sent)}

        return FakeResponse(requests_sent)

    def test_requests_out_of_order_second_errors(self):
        target_stitch.ourSession = FakeSession(mock_out_of_order_second_errors)
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        our_exception = None
        try:
            finish_requests()
        except Exception as ex:
            our_exception = ex

        self.assertIsNotNone(our_exception)
        self.assertTrue(isinstance(our_exception, TargetStitchException))

        emitted_state = self.out.getvalue().strip().split('\n')
        self.assertEqual(1, len(emitted_state))
        self.assertEqual({'bookmarks': {'chicken_stream': {'id': 1}}}, json.loads(emitted_state[0]))

if __name__== "__main__":
    test1 = AsyncPushToGate()
    test1.setUp()
    test1.test_requests_out_of_order_second_errors()
