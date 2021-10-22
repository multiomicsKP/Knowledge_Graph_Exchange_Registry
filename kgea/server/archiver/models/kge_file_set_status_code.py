# coding: utf-8

from kgea.server.web_services.models.base_model_ import Model
from kgea.server.web_services import util


class KgeFileSetStatusCode(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    """
    allowed enum values
    """
    CREATED = "Created"
    LOADED = "Loaded"
    PROCESSING = "Processing"
    VALIDATED = "Validated"
    ERROR = "Error"

    def __init__(self):
        """KgeFileSetStatusCode - a model defined in OpenAPI

        """
        self.openapi_types = {
        }

        self.attribute_map = {
        }

    @classmethod
    def from_dict(cls, dikt: dict) -> 'KgeFileSetStatusCode':
        """Returns the dict as a model

        :param dikt: A dict.
        :return: The KgeFileSetStatusCode of this KgeFileSetStatusCode.
        """
        return util.deserialize_model(dikt, cls)
