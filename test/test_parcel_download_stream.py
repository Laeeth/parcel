import os
import random
import string
import unittest

from mock import Mock
from parameterized import parameterized

from parcel.download_stream import DownloadStream


def random_string(length=10):
    return ''.join(
        random.choice(string.ascii_lowercase + string.ascii_uppercase)
        for _ in range(length))


def random_path(depth=2, name_length=10):
    return '/{}'.format('/'.join(random_string(name_length)
                        for _ in range(depth)))


CONTENT_DISPOSITION = 'attachment; filename={}'


class TestDownloadStreamGetInformation(unittest.TestCase):
    @parameterized.expand([
        ('Regular Name', random_string()),
        ('Path Name', random_path(depth=4)),
        ('Quotes in Filename', '"{}"'.format(random_string())),
        ('Quotes in Filename', "'{}'".format(random_string())),
        ('Quotes in Filename', '"{}"'.format(random_path())),
        ('Quotes in Filename', "'{}'".format(random_path()))
    ])
    def test_get_information_filename(self, _, file_path):
        ds = DownloadStream('http://example.com/something', 'some-directory',
                            'some-token')
        ds.request = Mock()
        r = Mock()
        disposition = CONTENT_DISPOSITION.format(file_path)
        r.headers = {
            'content-disposition': disposition,
        }
        ds.request.return_value = r

        # Actual call
        name, size = ds.get_information()

        # Assertions
        filename = os.path.basename(file_path.strip('"').strip("'"))
        self.assertEqual(ds.name, filename)
        self.assertEqual(ds.size, None)
        self.assertEqual(name, filename)
        self.assertEqual(size, None)

    @parameterized.expand([
        ('No Content-Length',
         {},
         {'size': None, 'md5sum': None, 'check_sum': False}),
        ('No md5sum',
         {'Content-Length': 1234},
         {'size': 1234, 'md5sum': '', 'check_sum': True}),
        ('Content-Length and md5sum',
         {'Content-Length': 1234, 'content-md5': 'abcd'},
         {'size': 1234, 'md5sum': 'abcd', 'check_sum': True}),
    ])
    def test_get_information_size_and_md5(self, _, headers, assertions):
        ds = DownloadStream('http://exmple.com/something', 'some-directory',
                            'some-token')

        ds.request = Mock()
        r = Mock()
        filename = random_string()
        disposition = CONTENT_DISPOSITION.format(filename)
        r.headers = headers
        r.headers['content-disposition'] = disposition
        ds.request.return_value = r

        # Actual call
        name, size = ds.get_information()

        # Assertions
        self.assertEqual(name, filename)
        self.assertEqual(ds.size, assertions.get('size'))
        self.assertEqual(size, assertions.get('size'))
        self.assertEqual(ds.check_file_md5sum, assertions.get('check_sum'))
        self.assertEqual(ds.md5sum, assertions.get('md5sum'))
