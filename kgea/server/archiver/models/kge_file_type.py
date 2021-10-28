# coding: utf-8

from kgea.server.archiver.models.base_model_ import Model
from kgea.server.archiver import util


class KgeFileType(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    """
    allowed enum values
    """
    UNKNOWN = "UNKNOWN"
    CONTENT_METADATA_FILE = "CONTENT_METADATA_FILE"
    DATA_FILE = "DATA_FILE"
    NODES = "NODES"
    EDGES = "EDGES"
    ARCHIVE = "ARCHIVE"

    def __init__(self):
        """KgeFileType - a model defined in OpenAPI

        """
        self.openapi_types = {
        }

        self.attribute_map = {
        }

    @classmethod
    def from_dict(cls, dikt: dict) -> 'KgeFileType':
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The KgeFileType of this KgeFileType.
        """
        return util.deserialize_model(dikt, cls)
