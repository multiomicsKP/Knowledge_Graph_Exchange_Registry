"""
Archiver service API handlers
"""

from aiohttp import web

from kgea.server.archiver.models import KgeFileSetMetadata
from kgea.server.archiver.kge_archiver_util import KgeArchiver

import logging

from kgea.server.catalog import KgeFileType, KgeFileSet
from kgea.server.kgea_session import report_bad_request

logger = logging.getLogger(__name__)


def _load_kge_file_set(metadata: KgeFileSetMetadata):
    """
    Loads in selected metadata of a KgeFileSet from a response data dictionary
    """
    fileset: KgeFileSet = KgeFileSet(
        kg_id=metadata.kg_id,
        fileset_version=metadata.fileset_version,
        biolink_model_release=metadata.biolink_model_release,
        date_stamp=metadata.date_stamp.strftime('%Y-%m-%d'),
        submitter_name=metadata.submitter_name,
        submitter_email=metadata.submitter_email,
        size=int(metadata.size * 1024 ** 2),
        status=metadata.status
    )
    for entry in metadata.files:
        file_name = entry.file_name
        object_key = f"{metadata.kg_id}/{metadata.fileset_version}/{file_name}"
        file_type = KgeFileType[entry.file_type]
        file_size = entry.file_size
        fileset.add_data_file(
            object_key=object_key,
            file_type=file_type,
            file_name=file_name,
            file_size=file_size
        )

    return fileset


async def process_kge_fileset(request: web.Request, metadata: KgeFileSetMetadata) -> web.Response:
    """Posts a KGE File Set for post-processing after upload.

    Posts a KGE File Set for post-processing after upload.

    :param request: includes the KGE File Set in the POST body, for processing.
    :type request: web.Request
    :param metadata: Metadata of the KGE File Set to be post-processed.
    :type metadata: KgeFileSetMetadata

    """
    file_set: KgeFileSet = _load_kge_file_set(metadata=metadata)

    process_token: str = ''
    try:
        archiver: KgeArchiver = KgeArchiver.get_archiver()
        process_token = await archiver.process(file_set)

    except Exception as error:
        msg = f"kge_archiver(): {str(error)}"
        await report_bad_request(request, msg)

    return web.json_response(text='{"process_token": "'+process_token+'"}')


async def get_kge_fileset_processing_status(request: web.Request, process_token: str) -> web.Response:
    """Get the progress of post-processing of a KGE File Set.

    Poll the status of a given post-processing task.

    :param request:
    :type request: web.Request
    :param process_token: Process token associated with a KGE File Set post-processing task.
    :type process_token: str

    """
    # TODO: Stub...Implement me!
    return web.json_response(text='{"process_token": "' + process_token + '"}')
