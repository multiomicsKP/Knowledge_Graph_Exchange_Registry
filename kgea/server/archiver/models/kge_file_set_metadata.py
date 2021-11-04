# coding: utf-8

from datetime import date

from typing import List

from kgea.server.archiver.models.base_model_ import Model
from kgea.server.archiver.models.kge_file import KgeFile
from kgea.server.archiver.models.kge_file_set_status_code import KgeFileSetStatusCode
from kgea.server.archiver import util


class KgeFileSetMetadata(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, kg_id: str=None, fileset_version: str=None, date_stamp: date=None, submitter_name: str=None, submitter_email: str=None, biolink_model_release: str=None, status: KgeFileSetStatusCode=None, files: List[KgeFile]=None, size: int=None):
        """KgeFileSetMetadata - a model defined in OpenAPI

        :param kg_id: The kg_id of this KgeFileSetMetadata.
        :param fileset_version: The fileset_version of this KgeFileSetMetadata.
        :param date_stamp: The date_stamp of this KgeFileSetMetadata.
        :param submitter_name: The submitter_name of this KgeFileSetMetadata.
        :param submitter_email: The submitter_email of this KgeFileSetMetadata.
        :param biolink_model_release: The biolink_model_release of this KgeFileSetMetadata.
        :param status: The status of this KgeFileSetMetadata.
        :param files: The files of this KgeFileSetMetadata.
        :param size: The size of this KgeFileSetMetadata.
        """
        self.openapi_types = {
            'kg_id': str,
            'fileset_version': str,
            'date_stamp': date,
            'submitter_name': str,
            'submitter_email': str,
            'biolink_model_release': str,
            'status': KgeFileSetStatusCode,
            'files': List[KgeFile],
            'size': int
        }

        self.attribute_map = {
            'kg_id': 'kg_id',
            'fileset_version': 'fileset_version',
            'date_stamp': 'date_stamp',
            'submitter_name': 'submitter_name',
            'submitter_email': 'submitter_email',
            'biolink_model_release': 'biolink_model_release',
            'status': 'status',
            'files': 'files',
            'size': 'size'
        }

        self._kg_id = kg_id
        self._fileset_version = fileset_version
        self._date_stamp = date_stamp
        self._submitter_name = submitter_name
        self._submitter_email = submitter_email
        self._biolink_model_release = biolink_model_release
        self._status = status
        self._files = files
        self._size = size

    @classmethod
    def from_dict(cls, dikt: dict) -> 'KgeFileSetMetadata':
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The KgeFileSetMetadata of this KgeFileSetMetadata.
        """
        return util.deserialize_model(dikt, cls)

    @property
    def kg_id(self):
        """Gets the kg_id of this KgeFileSetMetadata.

        Knowledge Graph identifier.

        :return: The kg_id of this KgeFileSetMetadata.
        :rtype: str
        """
        return self._kg_id

    @kg_id.setter
    def kg_id(self, kg_id):
        """Sets the kg_id of this KgeFileSetMetadata.

        Knowledge Graph identifier.

        :param kg_id: The kg_id of this KgeFileSetMetadata.
        :type kg_id: str
        """

        self._kg_id = kg_id

    @property
    def fileset_version(self):
        """Gets the fileset_version of this KgeFileSetMetadata.

        Semantic versioning of the version of the KGX File Set of the given knowledge graph.

        :return: The fileset_version of this KgeFileSetMetadata.
        :rtype: str
        """
        return self._fileset_version

    @fileset_version.setter
    def fileset_version(self, fileset_version):
        """Sets the fileset_version of this KgeFileSetMetadata.

        Semantic versioning of the version of the KGX File Set of the given knowledge graph.

        :param fileset_version: The fileset_version of this KgeFileSetMetadata.
        :type fileset_version: str
        """

        self._fileset_version = fileset_version

    @property
    def date_stamp(self):
        """Gets the date_stamp of this KgeFileSetMetadata.

        Date stamp of the file set.

        :return: The date_stamp of this KgeFileSetMetadata.
        :rtype: date
        """
        return self._date_stamp

    @date_stamp.setter
    def date_stamp(self, date_stamp):
        """Sets the date_stamp of this KgeFileSetMetadata.

        Date stamp of the file set.

        :param date_stamp: The date_stamp of this KgeFileSetMetadata.
        :type date_stamp: date
        """

        self._date_stamp = date_stamp

    @property
    def submitter_name(self):
        """Gets the submitter_name of this KgeFileSetMetadata.

        Name of the submitter of the KGE FileSet

        :return: The submitter_name of this KgeFileSetMetadata.
        :rtype: str
        """
        return self._submitter_name

    @submitter_name.setter
    def submitter_name(self, submitter_name):
        """Sets the submitter_name of this KgeFileSetMetadata.

        Name of the submitter of the KGE FileSet

        :param submitter_name: The submitter_name of this KgeFileSetMetadata.
        :type submitter_name: str
        """

        self._submitter_name = submitter_name

    @property
    def submitter_email(self):
        """Gets the submitter_email of this KgeFileSetMetadata.

        Email address for the submitter.

        :return: The submitter_email of this KgeFileSetMetadata.
        :rtype: str
        """
        return self._submitter_email

    @submitter_email.setter
    def submitter_email(self, submitter_email):
        """Sets the submitter_email of this KgeFileSetMetadata.

        Email address for the submitter.

        :param submitter_email: The submitter_email of this KgeFileSetMetadata.
        :type submitter_email: str
        """

        self._submitter_email = submitter_email

    @property
    def biolink_model_release(self):
        """Gets the biolink_model_release of this KgeFileSetMetadata.

        Biolink Model released associated with the file set.

        :return: The biolink_model_release of this KgeFileSetMetadata.
        :rtype: str
        """
        return self._biolink_model_release

    @biolink_model_release.setter
    def biolink_model_release(self, biolink_model_release):
        """Sets the biolink_model_release of this KgeFileSetMetadata.

        Biolink Model released associated with the file set.

        :param biolink_model_release: The biolink_model_release of this KgeFileSetMetadata.
        :type biolink_model_release: str
        """

        self._biolink_model_release = biolink_model_release

    @property
    def status(self):
        """Gets the status of this KgeFileSetMetadata.


        :return: The status of this KgeFileSetMetadata.
        :rtype: KgeFileSetStatusCode
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this KgeFileSetMetadata.


        :param status: The status of this KgeFileSetMetadata.
        :type status: KgeFileSetStatusCode
        """

        self._status = status

    @property
    def files(self):
        """Gets the files of this KgeFileSetMetadata.

        Annotated list of files within a given file set.

        :return: The files of this KgeFileSetMetadata.
        :rtype: List[KgeFile]
        """
        return self._files

    @files.setter
    def files(self, files):
        """Sets the files of this KgeFileSetMetadata.

        Annotated list of files within a given file set.

        :param files: The files of this KgeFileSetMetadata.
        :type files: List[KgeFile]
        """

        self._files = files

    @property
    def size(self):
        """Gets the size of this KgeFileSetMetadata.

        approximate aggregate size of data files in the file set (bytes)

        :return: The size of this KgeFileSetMetadata.
        :rtype: int
        """
        return self._size

    @size.setter
    def size(self, size):
        """Sets the size of this KgeFileSetMetadata.

        approximate aggregate size of data files in the file set (bytes)

        :param size: The size of this KgeFileSetMetadata.
        :type size: int
        """

        self._size = size
