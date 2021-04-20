# coding: utf-8

from datetime import date, datetime

from typing import List, Dict, Type

from web_services.models.base_model_ import Model
from web_services import util


class KgeFile(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, file_name: str=None, file_type: str=None, file_size: float=None):
        """KgeFile - a model defined in OpenAPI

        :param file_name: The file_name of this KgeFile.
        :param file_type: The file_type of this KgeFile.
        :param file_size: The file_size of this KgeFile.
        """
        self.openapi_types = {
            'file_name': str,
            'file_type': str,
            'file_size': float
        }

        self.attribute_map = {
            'file_name': 'file_name',
            'file_type': 'file_type',
            'file_size': 'file_size'
        }

        self._file_name = file_name
        self._file_type = file_type
        self._file_size = file_size

    @classmethod
    def from_dict(cls, dikt: dict) -> 'KgeFile':
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The KgeFile of this KgeFile.
        """
        return util.deserialize_model(dikt, cls)

    @property
    def file_name(self):
        """Gets the file_name of this KgeFile.

        original name of file (as uploaded)

        :return: The file_name of this KgeFile.
        :rtype: str
        """
        return self._file_name

    @file_name.setter
    def file_name(self, file_name):
        """Sets the file_name of this KgeFile.

        original name of file (as uploaded)

        :param file_name: The file_name of this KgeFile.
        :type file_name: str
        """

        self._file_name = file_name

    @property
    def file_type(self):
        """Gets the file_type of this KgeFile.

        designates if the file is meta-, node or edge data

        :return: The file_type of this KgeFile.
        :rtype: str
        """
        return self._file_type

    @file_type.setter
    def file_type(self, file_type):
        """Sets the file_type of this KgeFile.

        designates if the file is meta-, node or edge data

        :param file_type: The file_type of this KgeFile.
        :type file_type: str
        """

        self._file_type = file_type

    @property
    def file_size(self):
        """Gets the file_size of this KgeFile.

        size of file in megabytes

        :return: The file_size of this KgeFile.
        :rtype: float
        """
        return self._file_size

    @file_size.setter
    def file_size(self, file_size):
        """Sets the file_size of this KgeFile.

        size of file in megabytes

        :param file_size: The file_size of this KgeFile.
        :type file_size: float
        """

        self._file_size = file_size
