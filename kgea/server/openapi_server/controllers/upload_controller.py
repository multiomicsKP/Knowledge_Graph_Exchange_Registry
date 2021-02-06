from ..kgea_handlers import (
    get_kge_file_upload_form,
    get_kge_registration_form,
    register_kge_file_set,
    upload_kge_file_set,
)


def get_file_upload_form(session, submitter, kg_name):  # noqa: E501
    """Get web form for the KGE File Set upload process

     # noqa: E501

    :param session: 
    :type session: str
    :param submitter: 
    :type submitter: str
    :param kg_name: 
    :type kg_name: str

    :rtype: str
    """
    return get_kge_file_upload_form(session, submitter, kg_name)


def get_registration_form(session):  # noqa: E501
    """Prompt user for core parameters of the KGE File Set upload

     # noqa: E501

    :param session: 
    :type session: str

    :rtype: str
    """
    return get_kge_registration_form(session)


def register_file_set(body):  # noqa: E501
    """Register core parameters for the KGE File Set upload

     # noqa: E501

    :param session: 
    :type session: str
    :param submitter: 
    :type submitter: str
    :param kg_name: 
    :type kg_name: str

    :rtype: str
    """
    return register_kge_file_set(body)


def upload_file_set(kg_name, data_file_content, data_file_metadata=None):  # noqa: E501
    """Upload processing of KGE File Set

     # noqa: E501

    :param kg_name: 
    :type kg_name: str
    :param data_file_content: 
    :type data_file_content: str
    :param data_file_metadata: 
    :type data_file_metadata: str

    :rtype: str
    """
    return upload_kge_file_set(kg_name, data_file_content, data_file_metadata)
