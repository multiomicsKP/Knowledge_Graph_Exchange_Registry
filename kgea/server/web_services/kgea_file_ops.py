"""
Implement robust KGE File Set upload process:
o  “layered” back end unit tests of each level of S3 upload process
o  Figure out the minimal S3 access policy that suffices for the KGE Archive
o  File set versioning using time stamps
o  Web server optimization (e.g. NGINX / WSGI / web application parameters)
o  Test the system (both manually, by visual inspection of uploads)
Stress test using SRI SemMedDb: https://github.com/NCATSTranslator/semmeddb-biolink-kg
"""
from sys import stderr, exc_info
from typing import Union, List, Tuple, Dict, Optional
from subprocess import Popen, PIPE, STDOUT
from os import getenv
from os.path import sep, splitext, basename, dirname, abspath
import io
from asyncio import sleep
from pprint import PrettyPrinter

import random

import re
import itertools

import traceback
import logging

import requests
import smart_open
from datetime import datetime

from pathlib import Path
import tarfile

from validators import ValidationFailure, url as valid_url

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from botocore.config import Config
from boto3.s3.transfer import TransferConfig

from kgea.config import (
    PROVIDER_METADATA_FILE,
    FILE_SET_METADATA_FILE
)

from kgea.aws.assume_role import AssumeRole, aws_config
from kgea.aws.ec2 import get_ec2_instance_id, get_ec2_instance_availability_zone, get_ec2_instance_region

logger = logging.getLogger(__name__)

pp = PrettyPrinter(indent=4, stream=stderr)

# Master flag for local development, usually when code is not run inside an EC2 server
DEV_MODE = getenv('DEV_MODE', default=False)

s3_config = aws_config['s3']
default_s3_region = s3_config['region']
default_s3_bucket = s3_config['bucket']
default_s3_root_key = s3_config['archive-directory']

ebs_config: Dict = aws_config['ebs']
_SCRATCH_DEVICE = f"/dev/{ebs_config.setdefault('scratch_device', 'sdc')}"  # we assume that sdb is already used up?

# TODO: may need to fix script paths below - may not resolve under Microsoft Windows
# if sys.platform is 'win32':
#     archive_script = archive_script.replace('\\', '/').replace('C:', '/mnt/c/')

# Probably will rarely change the name of these scripts, but changed once already...
_SCRIPTS = f"{dirname(abspath(__file__))}{sep}scripts{sep}"
_SCRATCH_DIR = f"{_SCRIPTS}scratch"


def scratch_dir_path():
    return _SCRATCH_DIR


_KGEA_ARCHIVER_SCRIPT = f"{dirname(abspath(__file__))}{sep}scripts{sep}kge_archiver.bash"

_KGEA_EDA_SCRIPT = f"{_SCRIPTS}kge_extract_data_archive.bash"
_EDA_OUTPUT_DATA_PREFIX = "file_entry="  # the Decompress-In-Place bash script comment output data signal prefix

_KGEA_EBS_VOLUME_MOUNT_AND_FORMAT_SCRIPT = f"{_SCRIPTS}kge_ebs_volume_mount.bash"
_KGEA_EBS_VOLUME_UNMOUNT_SCRIPT = f"{_SCRIPTS}kge_ebs_volume_unmount.bash"


def print_error_trace(err_msg: str):
    """
    Print Error Exception stack
    """
    logger.error(err_msg)
    exc_type, exc_value, exc_traceback = exc_info()
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=stderr)


#############################################
# General Utility Functions for this Module #
#############################################
async def run_script(
        script,
        args: Tuple = (),
        # env: Optional = None
        stdout_parser=None
) -> int:
    """
    Run a given script in the background, with
     specified arguments and environment variables.

    :param script: full OS path to the executable script.
    :param args: command line arguments for the script
    :param stdout_parser: (optional) single string argument function to parse lines piped back from stdout of the script
    :return: return code of the script
    """
    cmd: List = list()
    cmd.append(script)
    cmd.extend(args)
    
    logger.debug(f"run_script(cmd: '{cmd}')")
    try:
        with Popen(
                args=cmd,
                # env=env,
                bufsize=1,
                universal_newlines=True,
                stdout=PIPE,
                stderr=STDOUT
        ) as proc:
            logger.info(f"run_script({script}) log:")
            for line in proc.stdout:
                line = line.strip()
                if stdout_parser:
                    stdout_parser(line)
                logger.debug(line)
                
    except RuntimeError:
        logger.error(f"run_script({script}) exception: {exc_info()}")
        return -1
    
    return proc.returncode


# https://www.askpython.com/python/examples/generate-random-strings-in-python
def random_alpha_string(length=8):
    """

    :param length:
    :return:
    """
    random_string = ''
    for _ in range(length):
        # Considering only upper and lowercase letters
        random_integer = random.randint(97, 97 + 26 - 1)
        flip_bit = random.randint(0, 1)
        # Convert to lowercase if the flip bit is on
        random_integer = random_integer - 32 if flip_bit == 1 else random_integer
        # Keep appending random characters using chr(x)
        random_string += (chr(random_integer))
    return random_string


def get_default_date_stamp():
    """
    Returns the default date stamp as 'now', as an ISO Format string 'YYYY-MM-DD'
    :return:
    """
    return datetime.now().strftime('%Y-%m-%d')


def infix_string(name, infix, delimiter="."):
    """

    :param name:
    :param infix:
    :param delimiter:
    :return:
    """
    tokens = name.split(delimiter)
    *pre_name, end_name = tokens
    name = ''.join([delimiter.join(pre_name), infix, delimiter, end_name])
    return name


def get_pathless_file_size(data_file):
    """
    Takes an open file-like object, gets its end location (in bytes),
    and returns it as a measure of the file size.

    Traditionally, one would use a systems-call to get the size
    of a file (using the `os` module). But `TemporaryFileWrapper`s
    do not feature a location in the filesystem, and so cannot be
    tested with `os` methods, as they require access to a filepath,
    or a file-like object that supports a path, in order to work.

    This function seeks the end of a file-like object, records
    the location, and then seeks back to the beginning so that
    the file behaves as if it was opened for the first time.
    This way you can get a file's size before reading it.

    (Note how we aren't using a `with` block, which would close
    the file after use. So this function leaves the file open,
    as an implicit non-effect. Closing is problematic for
     TemporaryFileWrappers which wouldn't be operable again)

    :param data_file:
    :return size:
    """
    if not data_file.closed:
        data_file.seek(0, 2)
        size = data_file.tell()
        logger.debug(size)
        data_file.seek(0, 0)
        return size
    else:
        return 0


def get_url_file_size(url: str) -> int:
    """
    Takes a URL specified resource, and gets its size (in bytes)

    :param url: resource whose size is being queried
    :return size:
    """
    size: int = 0
    if url:
        try:
            assert (valid_url(url))

            # fetching the header information
            info = requests.head(url)
            content_length = info.headers['Content-Length']
            size: int = int(content_length)
            return size
        except ValidationFailure:
            logger.error(f"get_url_file_size(url: '{str(url)}') is invalid?")
            return -2
        except KeyError:
            logger.error(f"get_url_file_size(url: '{str(url)}') doesn't have a 'Content-Length' value in its header?")
            return -3
        except Exception as exc:
            logger.error(f"get_url_file_size(url:'{str(url)}'): {str(exc)}")
            # TODO: invalidate the size invariant to propagate a call error
            # for now return -1 to encode the error state
            return -1

    return size


################################################
# Wrapper for AWS IAM Role for the Application #
################################################

# Obtain an AWS Clients using an Assumed IAM Role
# with default parameters (loaded from config.yaml)
#
the_role = AssumeRole()


############################
# AWS S3 client operations #
############################

def s3_client(
        assumed_role=None,
        config=Config(
            signature_version='s3v4',
            region_name=default_s3_region
        )
):
    """
    :param assumed_role: assumed IAM role serving as authentication broker
    :param config: botocore.config.Config configuring the S3 client
    :return: S3 client
    """
    
    if not assumed_role:
        assumed_role = the_role

    return assumed_role.get_client('s3', config=config)


def s3_resource(assumed_role=the_role, **kwargs):
    """
    :param assumed_role:
    :return: S3 resource
    """
    if not assumed_role:
        assumed_role = the_role

    if "region_name" not in kwargs:
        kwargs["region_name"] = default_s3_region

    return assumed_role.get_resource('s3', **kwargs)


def create_location(bucket, kg_id):
    """

    :param bucket:
    :param kg_id:
    :return:
    """
    return s3_client().put_object(Bucket=bucket, Key=get_object_location(kg_id))


def delete_location(bucket, kg_id):
    """

    :param bucket:
    :param kg_id:
    :return:
    """
    return s3_client().delete(Bucket=bucket, Key=get_object_location(kg_id))


def get_object_location(kg_id):
    """
    NOTE: Must be kept deterministic. No date times or
    randomness in this method; they may be appended afterwards.
    """
    location = f"{default_s3_root_key}/{kg_id}/"
    return location


# Don't use date stamp for versioning anymore
def with_version(func, version="1.0"):
    """

    :param func:
    :param version:
    :return:
    """

    def wrapper(kg_id):
        """

        :param kg_id:
        :return:
        """
        return func(kg_id + '/' + version), version

    return wrapper


def with_subfolder(location: str, subfolder: str):
    """

    :param location:
    :param subfolder:
    :return:
    """
    if subfolder:
        location += subfolder + '/'
    return location


def get_object_from_bucket(bucket_name, object_key):
    """

    :param bucket_name:
    :param object_key:
    :return:
    """
    bucket = s3_resource().Bucket(bucket_name)
    return bucket.Object(object_key)


def match_objects_from_bucket(bucket_name, object_key, assumed_role=None):
    """

    :param bucket_name:
    :param object_key:
    :param assumed_role:
    
    :return:
    """
    bucket = s3_resource(assumed_role=assumed_role).Bucket(bucket_name)
    key = object_key
    objs = list(bucket.objects.filter(Prefix=key))
    return [w.key == key for w in objs]


def object_key_exists(
        object_key,
        bucket_name=default_s3_bucket,
        assumed_role=None
) -> bool:
    """
    Checks for the existence of the specified object key

    :param bucket_name: The bucket
    :param object_key: Target object key in the bucket
    :param assumed_role: (optional) Assumed IAM Role with authority to make this inquiry

    :return: True if the object is in the bucket, False if it is not in the bucket (False also if empty object key)
    """
    if not object_key:
        return False
    return any(
        match_objects_from_bucket(
            bucket_name=bucket_name,
            object_key=object_key,
            assumed_role=assumed_role
        )
    )


def location_available(bucket_name, object_key) -> bool:
    """
    Predicate to guarantee that we can write to the
    location of the object without overriding everything.

    :param bucket_name: The bucket
    :param object_key: The object in the bucket
    :return: True if the object is not in the bucket, False if it is already in the bucket
    """
    if object_key_exists(object_key, bucket_name):
        # exists
        # invert because object key location is unavailable
        return False
    else:
        # doesn't exist
        # invert because object key location is available
        return True


def object_entries_in_location(bucket, object_location='') -> Dict[str, int]:
    """
    :param bucket:
    :param object_location:
    :return: dictionary of object entries with their size in specified
             object location in a bucket (all bucket entries if object_location is empty)
    """
    bucket_listings: Dict = dict()
    # logger.debug(s3_client().get_paginator("list_objects_v2").paginate(Bucket=bucket_name))
    for p in s3_client().get_paginator("list_objects_v2").paginate(Bucket=bucket):
        if 'Contents' in p:
            for entry in p['Contents']:
                bucket_listings[entry['Key']] = entry['Size']
        else:
            return {}  # empty bucket?

    # If object_location is the empty string, then each object
    # listed passes (since the empty string is part of every string)
    object_matches = {key: bucket_listings[key] for key in bucket_listings if object_location in key}
    
    return object_matches


def object_keys_in_location(bucket, object_location='') -> List[str]:
    """
    :param bucket:
    :param object_location:
    
    :return: all object keys in specified object location of a
             specified bucket (all bucket keys if object_location is empty)
    """
    key_catalog = object_entries_in_location(bucket, object_location=object_location)
    
    return list(key_catalog.keys())


def object_keys_for_fileset_version(
        kg_id: str,
        fileset_version: str,
        bucket=default_s3_bucket,
        match_function=lambda x: True
) -> Tuple[List[str], str]:
    """
    Returns a list of all the files associated with a
    given knowledge graph, for a given file set version.

    :param kg_id: knowledge graph identifier
    :param fileset_version: semantic version ('major.minor') of the file set
    :param bucket: target S3 bucket (default: current config.yaml bucket)
    :param match_function: (optional) lambda filter for list of file object keys returned

    :return: Tuple [ matched list of file object keys, file set version ] found
    """
    target_fileset, fileset_version = with_version(get_object_location, fileset_version)(kg_id)
    
    object_key_list: List[str] = \
        object_keys_in_location(
            bucket=bucket,
            object_location=target_fileset,
        )
    filtered_file_key_list = list(filter(match_function, object_key_list))
    
    return filtered_file_key_list, fileset_version


def object_folder_contents_size(
        kg_id: str,
        fileset_version: str,
        object_subfolder='',
        bucket=default_s3_bucket
) -> int:
    """
    :param kg_id: knowledge graph identifier
    :param fileset_version: semantic version ('major.minor') of the file set
    :param bucket: target S3 bucket (default: current config.yaml bucket)
    :param object_subfolder: subfolder path from root fileset path (default: empty - use fileset root path)

    :return: total size of archived files (in bytes)
    """
    target_fileset, fileset_version = with_version(get_object_location, fileset_version)(kg_id)
    target_folder = f"{target_fileset}{object_subfolder}"
    
    logger.debug(f"object_folder_contents_size({target_folder})")
    
    object_key_catalog: Dict[str, int] = \
        object_entries_in_location(
            bucket=bucket,
            object_location=target_folder,
        )

    total_size = 0
    for size in object_key_catalog.values():
        total_size += int(size)
    
    return total_size


# for an s3 key, match on kg_id
kg_ids_pattern = re.compile(rf"{default_s3_root_key}/([a-zA-Z\d \-]+)/.+")

# for an s3 key, match on kg_id and fileset version
kg_ids_with_versions_pattern = re.compile(rf"{default_s3_root_key}/([\S]+)/(\d+.\d+)/")


def get_fileset_versions_available(bucket_name):
    """
    A roster of all the versions that all knowledge graphs have been updated to.

    Input:
        - A list of object keys in S3 encoding knowledge graph objects
    Output:
        - A map of knowledge graph names to a list of their versions
    Tasks:
        - Extract the version from the knowledge graph path
        - Reduce the versions by knowledge graph name (a grouping)
        - Filter out crud data (like NoneTypes) to guarantee portability between server and client

    :param bucket_name:
    :return versions_per_kg: dict
    """

    all_kge_archive_files = \
        object_entries_in_location(
            bucket=bucket_name,
            object_location=default_s3_root_key
        )

    # create a map of kg_ids and their versions
    kg_ids = set(kg_ids_pattern.match(kg_file).group(1) for kg_file in all_kge_archive_files if
                 kg_ids_pattern.match(kg_file) is not None)  # some kg_ids don't have versions
    
    versions_per_kg = {}
    version_kg_pairs = set(
        (
            kg_ids_with_versions_pattern.match(kg_file).group(1),
            kg_ids_with_versions_pattern.match(kg_file).group(2)
        ) for kg_file in all_kge_archive_files if kg_ids_with_versions_pattern.match(kg_file) is not None)

    pp.pprint({"Knowledge Graphs": kg_ids, "File Set Versions": version_kg_pairs})

    for key, group in itertools.groupby(version_kg_pairs, lambda x: x[0]):
        versions_per_kg[key] = []
        for thing in group:
            versions_per_kg[key].append(thing[1])

    # add kg_ids that became filtered
    for kg_id in kg_ids:
        if kg_id not in versions_per_kg:
            versions_per_kg[kg_id] = []

    return versions_per_kg


# TODO: clarify expiration time - default to 1 day (in seconds)
def create_presigned_url(object_key, bucket=default_s3_bucket, expiration=86400) -> Optional[str]:
    """Generate a pre-signed URL to share an S3 object

    :param object_key: string
    :param bucket: string
    :param expiration: Time in seconds for the pre-signed URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """

    # Generate a pre-signed URL for the S3 object
    # https://stackoverflow.com/a/52642792
    #
    # This may throw a Boto related exception - assume that it will be caught by the caller
    #
    try:
        endpoint = s3_client().generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': bucket,
                'Key': object_key,
                'ResponseContentDisposition': 'attachment',
            },
            ExpiresIn=expiration
        )
    except Exception as e:
        logger.error("create_presigned_url() error: " + str(e))
        return None

    # The endpoint contains the pre-signed URL
    return endpoint


def kg_filepath(kg_id, fileset_version, root='', subdir='', attachment=''):
    """

    :param kg_id:
    :param fileset_version:
    :param root:
    :param subdir:
    :param attachment:
    :return:
    """
    return f"{root}/{kg_id}/{fileset_version}{subdir}/{attachment}"


# def package_file_manifest(tar_path):
#     """
#
#     :param tar_path:
#     :return:
#     """
#     with tarfile.open(tar_path, 'r|gz') as tar:
#         manifest = dict()
#         for tarinfo in tar:
#             logger.debug("\t", tarinfo.name, "is", tarinfo.size, "bytes in size and is ", end="")
#             if tarinfo.isreg():
#                 logger.debug("a regular file.")
#             elif tarinfo.isdir():
#                 logger.debug("a directory.")
#             else:
#                 logger.debug("something else.")
#             manifest[tarinfo.name] = {
#                 "raw": tarinfo,
#                 "name": tarinfo.name,
#                 "type": tarinfo.type,
#                 "size": tarinfo.size
#             }
#         return manifest


def get_object_key(object_location, filename):
    """
    :param object_location: S3 location of the persisted object
    :param filename: filename of the S3 object
    :return: object key of the S3 object
    """
    return f"{object_location}{Path(filename).stem}{splitext(filename)[1]}"


def upload_file(bucket, object_key, source, client=s3_client(), config=None, callback=None):
    """
    Upload a file to an S3 bucket. Note that this method is
    totally agnostic as to specific (KGX) file format and content.

    :param bucket: Bucket to upload to
    :param object_key: target S3 object key of the file.
    :param source: file to be uploaded (can be read in binary mode)
    :param client: The s3 client to use. Useful if needing to make a new client for the sake of thread safety.
    :param config: a means of configuring the network call
    :param callback: an object that implements __call__, that runs on each file block uploaded (receiving byte data.)

    :raises RuntimeError if the S3 file object upload call fails
    """

    # Upload the file
    try:
        # TODO: how can these upload calls be aborted, especially, if they are multi-part uploads?
        #       Maybe we need to use lower level multi-part upload functions here? What if the file is small?
        if config is None:
            client.upload_fileobj(source, bucket, object_key, Callback=callback)
        else:
            client.upload_fileobj(source, bucket, object_key, Config=config, Callback=callback)
    except Exception as exc:
        logger.warning("kgea_file_ops.upload_file(): " + str(exc))
        # TODO: what sort of post-cancellation processing is needed here?


def upload_file_multipart(
        data_file,
        file_name,
        bucket,
        object_location,
        metadata=None,
        callback=None,
        client=s3_client()
):
    """Upload a file to an S3 bucket. Use multipart protocols.
    Multipart transfers occur when the file size exceeds the value of the multipart_threshold attribute

    :param data_file: File to upload
    :param file_name: Name of file to upload
    :param bucket: Bucket to upload to
    :param object_location: S3 object name
    :param metadata: metadata associated with the file
    :param callback: Callable to track number of bytes being uploaded
    :param client: The s3 client to use. Useful if needing to make a new client for the sake of thread safety.
    """

    """
    Multipart file upload configuration

    Test Values:
    MP_THRESHOLD = 10
    MP_CONCURRENCY = 5
    """
    MP_THRESHOLD = 10
    MP_CHUNK = 8  # MPU threshold 8 MB at a time for production AWS transfers
    MP_CONCURRENCY = 5

    KB = 1024
    MB = KB * KB
    # GB = MB ** 3

    mp_threshold = MP_THRESHOLD * MB
    mp_chunk = MP_CHUNK * MB
    concurrency = MP_CONCURRENCY

    transfer_config = TransferConfig(
        multipart_threshold=mp_threshold,
        multipart_chunksize=mp_chunk,
        use_threads=True,
        max_concurrency=concurrency
    )
    object_key = get_object_key(object_location, file_name)
    upload_file(
        bucket=bucket,
        object_key=object_key,
        source=data_file,
        client=client,
        config=transfer_config,
        callback=callback
    )
    return object_key


async def compress_fileset(
        kg_id,
        version,
        bucket=default_s3_bucket,
        root=default_s3_root_key
) -> str:
    """
    :param kg_id:
    :param version:
    :param bucket:
    :param root:
    :return:
    """
    s3_archive_key = f"s3://{bucket}/{root}/{kg_id}/{version}/archive/{kg_id + '_' + version}.tar.gz"

    logger.debug(f"Initiating execution of compress_fileset({s3_archive_key})")

    try:
        return_code = await run_script(
            script=_KGEA_ARCHIVER_SCRIPT,
            args=(bucket, root, kg_id, version)
        )
        logger.info(f"Finished archive script build {s3_archive_key}, return code: {str(return_code)}")
        
    except Exception as e:
        logger.error(f"compress_fileset({s3_archive_key}) exception: {str(e)}")

    logger.debug(f"Exiting compress_fileset({s3_archive_key})")
    
    return s3_archive_key


async def extract_data_archive(
        kg_id: str,
        file_set_version: str,
        archive_filename: str,
        bucket: str = default_s3_bucket,
        root_directory: str = default_s3_root_key
) -> List[Dict[str, str]]:
    """
    Decompress a tar.gz data archive file from a given S3 bucket, and upload back its internal files back.
    
    Version 1.0 - decompress_in_place() below used Smart_Open... not scalable
    Version 2.0 - this version uses an external bash shell script to perform this operation...

    :param kg_id: knowledge graph identifier to which the archive belongs
    :param file_set_version: file set version to which the archive belongs
    :param archive_filename: base name of the tar.gz archive to be decompressed
    :param bucket: in S3
    :param root_directory: KGE data folder in the bucket
    
    :return: list of file entries
    """
    # one step decompression - bash level script operations on the local disk
    logger.debug(f"Initiating execution of extract_data_archive({archive_filename})")
    
    if not archive_filename.endswith('.tar.gz'):
        err_msg = f"archive name '{str(archive_filename)}' is not a 'tar.gz' archive?"
        logger.error(err_msg)
        raise RuntimeError(f"extract_data_archive(): {err_msg}")

    part = archive_filename.split('.')
    archive_filename = '.'.join(part[:-2])
    
    file_entries: List[Dict[str, str]] = []

    def output_parser(line: str):
        """
        :param line: bash script stdout line being parsed
        """
        if not line.strip():
            return   # empty line?
        
        # logger.debug(f"Entering output_parser(line: {line})!")
        if line.startswith(_EDA_OUTPUT_DATA_PREFIX):
            line = line.replace(_EDA_OUTPUT_DATA_PREFIX, '')
            file_name, file_type, file_size, file_object_key = line.split(',')
            logger.debug(f"DDA script file entry: {file_name}, {file_type}, {file_size}, {file_object_key}")
            file_entries.append({
                "file_name": file_name,
                "file_type": file_type,
                "file_size": str(file_size),
                "object_key": file_object_key
            })
    try:
        return_code = await run_script(
            script=_KGEA_EDA_SCRIPT,
            args=(
                bucket,
                root_directory,
                kg_id,
                file_set_version,
                archive_filename
            ),
            stdout_parser=output_parser
        )
        logger.debug(f"Completed extract_data_archive({archive_filename}.tar.gz), with return code {str(return_code)}")
        
    except Exception as e:
        logger.error(f"decompress_in_place({archive_filename}.tar.gz): exception {str(e)}")
    
    logger.debug(f"Exiting decompress_in_place({archive_filename}.tar.gz)")

    return file_entries


def decompress_in_place(tar_gz_file_key, target_location=None, traversal_func=None):
    """
    ### DEPRECIATED - see extract_data_archive() above.
    
    Decompress a gzipped file from within a given S3 bucket.

    Version 1.0 - this version used Smart_Open... not scalable
    Version 2.0 - extract_data_archive above uses an external bash shell script to perform this operation...

    Can take a custom location to stop the unpacking from being in
    the location of the gzipped file, but instead done somewhere else.

    Can take a traversal function to customize the distribution
    of unpacked files into different folders.

    :param tar_gz_file_key: The S3 key for the gzipped archive
    :param target_location: The location to which to unpack (not necessarily the root folder of the gzipped file)
    :param traversal_func: Optional
    :return:
    """
    
    if target_location[-1] != '/':
        raise Warning(
            "decompress_to_kgx(): the target location given doesn't terminate in a separator, " +
            f" instead {target_location[-1]}." +
            "\nUnarchived files may be put outside of a <kg_id>/<fileset_version>/ folder pair."
        )
    
    if '.gz' not in tar_gz_file_key:
        raise Exception('decompress_in_place(): Gzipped key cannot be a GZIP file! (' + str(tar_gz_file_key) + ')')
    
    if target_location is None:
        target_location = '/'.join(tar_gz_file_key.split('/')[:-1]) + '/'
    
    archive_location = f"s3://{default_s3_bucket}/{tar_gz_file_key}"
    
    file_entries = []
    
    # one step decompression - use the tarfile library's ability
    # to open gzip files transparently to avoid gzip+tar step
    with smart_open.open(archive_location, 'rb', compression='disable') as fin:
        with tarfile.open(fileobj=fin) as tf:
            if traversal_func is not None:
                logger.debug('decompress_in_place(): traversing the archive with a custom traversal function')
                file_entries = traversal_func(tf, target_location)
            else:
                for entry in tf:  # list each entry one by one
                    fileobj = tf.extractfile(entry)
                    
                    # problem: entry name file can be is nested. un-nest. Use os path to get the flat file name
                    unpacked_filename = basename(entry.name)
                    
                    if fileobj is not None:  # not a directory
                        s3_client().upload_fileobj(  # upload a new obj to s3
                            Fileobj=io.BytesIO(fileobj.read()),
                            Bucket=default_s3_bucket,  # target bucket, writing to
                            Key=target_location + unpacked_filename
                        )
                        file_entries.append({
                            "file_type": "KGX data file",  # TODO: refine to more specific types?
                            "file_name": unpacked_filename,
                            "file_size": entry.size,
                            "object_key": target_location + unpacked_filename
                        })
    return file_entries


# KGE filename regex patterns pre-compiled
node_file_pattern = re.compile('node[s]?.tsv')  # a node file by its own admission
node_folder_pattern = re.compile('nodes/')  # a nodes file given where it's placed
edge_file_pattern = re.compile('edge[s]?.tsv')  # an edge file by its own admission
edge_folder_pattern = re.compile('edges/')  # an edges file given where it's placed
metadata_file_pattern = re.compile(r'content_metadata\.json')
metadata_folder_pattern = re.compile('metadata/')


def decompress_to_kgx(gzipped_key, location, strict=False, prefix=True):
    # TODO: implement strict
    """
        ### DEPRECIATED - see extract_data_archive() above.

    Decompress a gzip'd file which was uploaded to a given S3 bucket.
    If it contains a nodes or edges file, place them into their
    corresponding folders within the knowledge graph working directory.

    For instance:
    - if the tarfile has a file `./nodes/kgx-1.tsv`, it goes into the nodes/ folder. Similarly with edges.
    - if the tarfile has a file `node.tsv`, it goes into the nodes/ folder. Similarly with edges.
    - if the tarfile has a file `metadata/content.json`, it fails to upload the file as metadata.
    - if the tarfile has a file `metadata/content_metadata.json`, it goes into the metadata/ folder(?)

    For anything else, if `strict` is False, then these other files are  uploaded to the key given by `location`.

    If `strict` is true, only node, edge or metadata files are added to this `location`, modulo the conventions above.

    This decompression function is used as a way of standardizing the uploaded archives into KGX graphs. When used
    strictly, it should help ensure that only KGX-validatable data occupies the final archive. When used un-strictly,
    it allows for a loose conception of archives that lets them be not necessarily validatable by KGX. This notion
    is preferred in the case where an archive's data is useful, but still needs to work towards being KGX-compliant.

    :param gzipped_key: The S3 key for the gzipped archive
    :param location: The location to unpack onto (not necessarily the root folder of the gzipped file)
    :param strict:
    :param prefix:
    :return:
    """

    if location[-1] != '/':
        raise Warning(
            f"decompress_to_kgx(): the location given doesn't terminate in a separator, instead {location[-1]}." +
            "\nUnarchived files may be put outside of a <kg_id>/<fileset_version>/ folder pair."
        )

    logger.debug('decompress_to_kgx(): Decompress the archive as if it is a KGX file')

    # check for node-yness or edge-yness
    # a tarfile entry is node-y if it's packed inside a nodes folder,
    # or has the word "node" in it towards the end of the filename
    def is_node_y(entry_name):
        """
        :param entry_name:
        :return:
        """
        return node_file_pattern.match(entry_name) is not None or \
               node_folder_pattern.match(entry_name) is not None

    # a tarfile entry is edge-y if it's packed inside an edges folder,
    # or has the word "edge" in it towards the end of the filename
    def is_edge_y(entry_name):
        """
        :param entry_name:
        :return:
        """
        return edge_file_pattern.match(entry_name) is not None or \
               edge_folder_pattern.match(entry_name) is not None

    def is_metadata(entry_name):
        """
        :param entry_name:
        :return:
        """
        return metadata_file_pattern.match(entry_name) is not None or edge_folder_pattern.match(entry_name) is not None

    def traversal_func_kgx(tf, location):
        """

        :param tf:
        :param location:
        :return:
        """
        logger.debug(f"traversal_func_kgx(): Begin traversing across the archive for nodes and edge files'{tf}'")

        file_entries = []
        for entry in tf:  # list each entry one by one
            
            logger.debug(f"traversal_func_kgx(): Traversing entry'{entry}'")

            object_key = location  # if not strict else None
            
            fileobj = tf.extractfile(entry)

            logger.debug(f"traversal_func_kgx(): Entry file object '{fileobj}'")

            if fileobj is not None:  # not a directory
                
                pre_name = entry.name
                unpacked_filename = basename(pre_name)

                logger.debug(f"traversal_func_kgx(): Entry names: {pre_name}, {unpacked_filename}")
                
                if is_node_y(pre_name):
                    object_key = location + 'nodes/' + unpacked_filename
                elif is_edge_y(pre_name):
                    object_key = location + 'edges/' + unpacked_filename
                else:
                    object_key = location + unpacked_filename

                logger.debug(f"traversal_func_kgx(): Object key will be '{object_key}'")

                if object_key is not None:
                    
                    logger.debug(f"traversal_func_kgx(): uploading entry into '{object_key}'")

                    s3_client().upload_fileobj(  # upload a new obj to s3
                        Fileobj=io.BytesIO(fileobj.read()),
                        Bucket=default_s3_bucket,  # target bucket, writing to
                        Key=object_key  # TODO was this a bug before? (when it was location + unpacked_filename)
                    )

                    file_entries.append({
                        "file_type": "KGX data file",  # TODO: refine to more specific types?
                        "file_name": unpacked_filename,
                        "file_size": entry.size,
                        "object_key": object_key
                    })

        logger.debug(f"traversal_func_kgx(): file entries: '{file_entries}'")

        return file_entries

    return decompress_in_place(gzipped_key, location, traversal_func_kgx)


def aggregate_files(
        target_folder,
        target_name,
        file_object_keys,
        bucket=default_s3_bucket,
        match_function=lambda x: True
) -> str:
    """
    Aggregates files matching a match_function.

    :param bucket:
    :param target_folder:
    :param target_name: target data file format(s)
    :param file_object_keys:
    :param match_function:
    :return:
    """
    if not file_object_keys:
        return ''

    agg_path = f"s3://{bucket}/{target_folder}/{target_name}"
    logger.debug(f"agg_path: {agg_path}")
    with smart_open.open(agg_path, 'w', encoding="utf-8", newline="\n") as aggregated_file:
        file_object_keys = list(filter(match_function, file_object_keys))
        for index, file_object_key in enumerate(file_object_keys):
            target_key_uri = f"s3://{bucket}/{file_object_key}"
            with smart_open.open(target_key_uri, 'r', encoding="utf-8", newline="\n") as subfile:
                for line in subfile:
                    aggregated_file.write(line)
                if index < (len(file_object_keys) - 1):  # only add newline if it isn't the last file. -1 for zero index
                    aggregated_file.write("\n")

    return agg_path


def copy_file(
        source_key,
        target_dir,
        bucket=default_s3_bucket
):
    """
    Copies source_key text file into target_dir

    :param bucket:
    :param source_key:
    :param target_dir:
    :return:
    """
    if not (source_key and target_dir):
        raise RuntimeError("copy_file_to_archive(): missing source_key or target_dir?")

    source_file_name = source_key.split("/")[-1]
    target_key = f"{target_dir}/{source_file_name}"

    logger.debug(f"Copying {source_key} to {target_key}")

    copy_source = {
        'Bucket': bucket,
        'Key': source_key
    }
    s3_client().copy(copy_source, bucket, target_key)

    logger.debug(f"...copy completed!")


def load_s3_text_file(bucket_name: str, object_name: str, mode: str = 'text') -> Union[None, bytes, str]:
    """
    Given an S3 object key name, load the specific file.
    The return value defaults to being decoded from utf-8 to a text string.
    Return None the object is inaccessible.
    """
    data_string: Union[None, bytes, str] = None

    try:
        mf = io.BytesIO()
        s3_client().download_fileobj(
            bucket_name,
            object_name,
            mf
        )
        data_bytes = mf.getvalue()
        mf.close()
        if mode == 'text':
            data_string = data_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"ERROR: _load_s3_text_file('{str(e)}')")

    return data_string


def get_archive_contents(bucket_name: str) -> \
        Dict[
            str,  # kg_id's of every KGE archived knowledge graph
            Dict[
                str,  # tags 'metadata' and 'versions'
                Union[
                    str,  # 'metadata' field value: kg specific 'provider' text file blob from S3
                    Dict[
                        str,  # fileset_version's of versioned KGE File Sets for a kg
                        Dict[
                            str,  # tags 'metadata' and 'file_object_keys'
                            Union[
                                str,  # 'metadata' field value: 'file set' specific text file blob from S3
                                List[str]  # list of data files in a given KGE File Set
                            ]
                        ]
                    ]
                ]
            ]
        ]:
    """
    Get contents of KGE Archive from the
    AWS S3 bucket folder names and metadata file contents.

    :param bucket_name: The bucket
    :return: multi-level catalog of KGE knowledge graphs and associated versioned file sets from S3 storage
    """
    all_object_keys = object_keys_in_location(bucket=bucket_name)

    contents: Dict[
        str,  # kg_id's of every KGE archived knowledge graph
        Dict[
            str,  # tags 'metadata' and 'versions'
            Union[
                str,  # 'metadata' field value: kg specific 'provider' text file blob from S3
                Dict[
                    str,  # fileset_version's of versioned KGE File Sets for a kg
                    Dict[
                        str,  # tags 'metadata' and 'file_object_keys'
                        Union[
                            str,  # 'metadata' field value: 'file set' specific text file blob from S3
                            List[str]  # list of data file object keys in a given KGE File Set
                        ]
                    ]
                ]
            ]
        ]
    ] = dict()

    for file_path in all_object_keys:

        file_part = file_path.split('/')

        if not file_part:
            continue

        # ignore things that don't look like the KGE File Set folder
        if file_part[0] != default_s3_root_key:
            continue

        # ignore empty KGE File Set folder
        if len(file_part) == 1 or not file_part[1]:
            continue

        kg_id = file_part[1]
        if kg_id not in contents:
            # each Knowledge Graph may have high level 'metadata'
            # obtained from a kg_id specific PROVIDER_METADATA_FILE
            # plus one or more versions of KGE File Set
            contents[kg_id] = dict()  # dictionary of kg's, indexed by kg_id
            contents[kg_id]['versions'] = dict()  # dictionary of versions, indexed by fileset_version

        if file_part[2] == PROVIDER_METADATA_FILE:
            # Get the provider 'kg_id' associated metadata file just stored
            # as a blob of text, for content parsing by the function caller
            # Unlike the kg_id versions, there should only be one such file?
            contents[kg_id]['metadata'] = \
                load_s3_text_file(
                    bucket_name=bucket_name,
                    object_name=file_path
                )
            # we ignore this file in the main versioned file list
            # since it is global to the knowledge graph.  In fact,
            # sometimes, the fileset_version may not yet be properly set!
            continue

        else:
            # otherwise, assume file_part[2] is a 'version folder'
            fileset_version = file_part[2]
            if fileset_version not in contents[kg_id]['versions']:
                contents[kg_id]['versions'][fileset_version] = dict()
                contents[kg_id]['versions'][fileset_version]['file_object_keys'] = list()

            # if the fileset versioned object key is not empty?
            if len(file_part) >= 4:
                if file_part[3] == FILE_SET_METADATA_FILE:
                    # Get the provider 'kg_id' associated metadata file just stored
                    # as a blob of text, for content parsing by the function caller
                    # Unlike the kg_id versions, there should only be one such file?
                    contents[kg_id]['versions'][fileset_version]['metadata'] = \
                        load_s3_text_file(
                            bucket_name=bucket_name,
                            object_name=file_path
                        )
                    continue

                # simple first iteration just records the list of data file paths
                # (other than the PROVIDER_METADATA_FILE and FILE_SET_METADATA_FILE)
                # TODO: how should subfolders (i.e. 'nodes' and 'edges') be handled?
                contents[kg_id]['versions'][fileset_version]['file_object_keys'].append(file_path)
    return contents


# Curl Bytes Received
_cbr_pattern = re.compile(r"^(?P<num>\d+(\.\d+)?)(?P<mag>[KMGTP])?$", flags=re.IGNORECASE)
_cbr_magnitude = {
    'K': 2**10,
    'M': 2**20,
    'G': 2**30,
    'T': 2**40,
    'P': 2**50,
}


def _cbr(value) -> int:
    """
    Symbolic Curl Bytes Received string, parsed to int
    :param value:
    :return:
    """
    m = _cbr_pattern.match(value)
    if m:
        if m.group('mag'):
            return round(float(m.group('num')) * _cbr_magnitude[m.group('mag').upper()])
        else:
            return round(float(m.group('num')))
    else:
        return -1


def upload_from_link(
        bucket,
        object_key,
        source,
        client=None,  # not used here. EC2 level aws cli used instead
        callback=None
):
    """
    Transfers a file resource to S3 from a URL location. Note that this
    method is totally agnostic as to specific (KGX) file format and content.

    :param bucket: in S3
    :param object_key: of target S3 object
    :param source: url of resource to be uploaded to S3
    :param callback: e.g. progress monitor
    :param client: for S3 - ignored (aws CLI used instead)
    """
    # make sure we're getting a valid url
    assert(valid_url(source))
    
    try:
        
        s3_object_target = f"s3://{bucket}/{object_key}"
        cmd = f"curl -L {source}| aws s3 cp - {s3_object_target}"
        with Popen(
            cmd,
            bufsize=1,
            universal_newlines=True,
            stderr=PIPE,
            shell=True
        ).stderr as proc_stderr:
            previous: int = 0
            callback(0)
            for line in proc_stderr:
                # The 'line' is the full curl progress meter
                field = line.split()
                if not field:
                    continue
                current: int = _cbr(field[3])
                if current < 0:
                    continue
                if previous < current:
                    callback(current-previous)
                    previous = current
        
    except RuntimeWarning:
        logger.warning("URL transfer cancelled by exception?")


###################################
# AWS EC2 & EBS client operations #
###################################

def ec2_client(
        assumed_role=None,
        config=Config(
            # EC2 region assumed to be set to the same as the
            # config.yaml S3, but not totally sure about this.
            region_name=default_s3_region
        )
):
    """
    :param assumed_role: assumed IAM role serving as authentication broker
    :param config: botocore.config.Config configuring the EC2 client
    :return: AWS EC2 client
    """
    if not assumed_role:
        assumed_role = the_role
    return assumed_role.get_client('ec2', config=config)


def ec2_resource(assumed_role=the_role, **kwargs):
    """
    :param assumed_role:
    :return: EC2 resource
    """

    if not assumed_role:
        assumed_role = the_role

    return assumed_role.get_resource('ec2', **kwargs)

###################################################################################################
# Dynamic EBS provisioning steps, orchestrated by the KgeArchiver.worker() task which
# direct calls methods using S3 and EC2 clients, plus an (steps 1.3, 1.4 plus 3.1) enhanced
# version of the (step 2.0) kgea/server/web_services/scripts/kge_archiver.bash script.
#
# object_folder_contents_size():
# 0.1 (S3 client) - Calculate EBS storage needs for target activity
# (step 2.0 - archiving.. see below), then proceed to step 1.1
#
# create_ebs_volume():
# 1.1 (EC2 client) - Create a suitably sized EBS volume, via the EC2 client
# 1.2 (EC2 client) - Associate the EBS volume with the EC2 instance running the application
# 1.3 (Popen() run bash script) - Mount the EBS volume inside the EC2 instance and format the volume
#     TODO: might try to configure and use a persistent EBS Snapshot in step 1 to accelerate this step?
#     TODO: what kind of unit testing can I attempt on the dynamic EBS provisioning subsystem?
#     TODO: in the DOCKER containers, you may need to map the dynamically provisioned EBS 'scratch' directory
#     TODO: begs the question: why copy the source code into the docker container? Should it simply be a mapped volume?
#
# compress_fileset():
# 2.0 (Popen() run bash script) - Use the instance as the volume working space for target
#     application activities (i.e. archiving). Likely need to set or change to the
#     current working directory to one hosted on the target EBS volume.
#
# delete_ebs_volume():
# 3.1 (Popen() run bash script) - Cleanly unmount EBS volume after it is no longer needed.
# 3.2 (EC2 client) - Disassociate the EBS volume from the EC2 instance.
# 3.3 (EC2 client) - Delete the instance (to avoid economic cost).
###################################################################################################


async def create_ebs_volume(
        size: int,
        device: str = _SCRATCH_DEVICE,
        mount_point: str = scratch_dir_path(),
        dry_run: bool = False
) -> Optional[str]:
    """
    Allocates and mounts an EBS volume of a given size onto the EC2 instance running the application (if applicable).
    The EBS volume is mounted by default on the (Linux) directory '/data' and formatted as a simple
    
    Notes:
    * This operation can only be performed when the application is running inside an EC2 instance
    
    :param size: specified size (in gigabytes)
    :param device: EBS device path of volume to be deleted (default: config.yaml designated 'scratch' device name)
    :param mount_point: OS mount point (path) from which to unmount the volume (default: local 'scratch' mount point)
    :param dry_run: no operation test run if True

    :return: EBS volume instance identifier (or TODO: maybe better to return UUID of formatted volume?)
    """
    # The application can only create an EBS volume if it is running
    # within an EC2 instance so retrieve the EC2 instance identifier
    instance_id = get_ec2_instance_id()
    if not (dry_run or instance_id):
        logger.warning(
            "create_ebs_volume(): not inside an EC2 instance? Cannot dynamically provision your EBS volume?"
        )
        return None

    logger.debug(f"create_ebs_volume(): creating an EBS volume of size '{size}' GB for instance {instance_id}.")

    ec2_region = get_ec2_instance_region()
    ec2_availability_zone = get_ec2_instance_availability_zone()

    try:
        ebs_ec2_client = ec2_client(config=Config(region_name=ec2_region))

        # Create a suitably sized EBS volume, via the EC2 client
        # response == {
        #     'Attachments': [
        #         {
        #             'AttachTime': datetime(2015, 1, 1),
        #             'Device': 'string',
        #             'InstanceId': 'string',
        #             'State': 'attaching'|'attached'|'detaching'|'detached'|'busy',
        #             'VolumeId': 'string',
        #             'DeleteOnTermination': True|False
        #         },
        #     ],
        #     'AvailabilityZone': 'string',
        #     'CreateTime': datetime(2015, 1, 1),
        #     'Encrypted': True|False,
        #     'KmsKeyId': 'string',
        #     'OutpostArn': 'string',
        #     'Size': 123,
        #     'SnapshotId': 'string',
        #     'State': 'creating'|'available'|'in-use'|'deleting'|'deleted'|'error',
        #     'VolumeId': 'string',
        #     'Iops': 123,
        #     'Tags': [
        #         {
        #             'Key': 'string',
        #             'Value': 'string'
        #         },
        #     ],
        #     'VolumeType': 'standard'|'io1'|'io2'|'gp2'|'sc1'|'st1'|'gp3',
        #     'FastRestored': True|False,
        #     'MultiAttachEnabled': True|False,
        #     'Throughput': 123
        # }
        volume_info = ebs_ec2_client.create_volume(
            AvailabilityZone=ec2_availability_zone,
            Size=size,
            VolumeType='gp2',
            DryRun=dry_run,
        )
        logger.debug(f"create_ebs_volume(): ec2_client.create_volume() response:\n{pp.pformat(volume_info)}")

        volume_id = volume_info["VolumeId"]
        volume_status = volume_info["State"]

        # monitor status for 'available' before proceeding
        while volume_status not in ["available", "error"]:

            # Wait a little while for completion of volume creation...
            await sleep(1)

            # ... then check status again
            volume_status = ebs_ec2_client.describe_volumes(
                Filters=[
                    {
                        'Name': 'status',
                        'Values': [
                            'creating',
                            'available',
                            'in-use',
                            'deleting',
                            'deleted',
                            'error'
                        ]
                    },
                ],
                VolumeIds=[volume_id],
                DryRun=dry_run
            )
            logger.debug(
                f"create_ebs_volume(): ebs_ec2_client.describe_volumes() response:\n{pp.pformat(volume_status)}"
            )
            volume_status = volume_status['State']

        if volume_status == "error":
            logger.error(f"create_ebs_volume(): for some reason, volume State is in 'error'")
            return None

    except Exception as ex:
        logger.error(f"create_ebs_volume(): ec2_client.create_volume() exception: {str(ex)}")
        return None

    logger.debug(f"create_ebs_volume(): executing ec2_resource().Volume({volume_id})")
    volume = ec2_resource(region_name=ec2_region).Volume(volume_id)

    # Attach the EBS volume to a device in the EC2 instance running the application
    try:
        # va_response == {
        #     'AttachTime': datetime(2015, 1, 1),
        #     'Device': 'string',
        #     'InstanceId': 'string',
        #     'State': 'attaching'|'attached'|'detaching'|'detached'|'busy',
        #     'VolumeId': 'string',
        #     'DeleteOnTermination': True|False
        # }
        logger.debug(
            "create_ebs_volume(): executing " +
            f"volume.attach_to_instance(Device={device}, InstanceId={instance_id}, DryRun={dry_run})"
        )
        va_response = volume.attach_to_instance(
            Device=device,
            InstanceId=instance_id,
            DryRun=dry_run
        )
        logger.debug(f"create_ebs_volume(): volume.attach_to_instance() response:\n{pp.pformat(va_response)}")
    except Exception as e:
        logger.error(
            f"create_ebs_volume(): failed to attach EBS volume '{volume_id}' to instance '{instance_id}': {str(e)}"
        )
        return None

    logger.debug(
        f"create_ebs_volume(): Attempting to mount and format EBS volume '{volume_id}' onto '{mount_point}'."
    )

    try:
        if not dry_run:
            return_code = await run_script(
                script=_KGEA_EBS_VOLUME_MOUNT_AND_FORMAT_SCRIPT,
                args=(volume_id, mount_point)
            )
            if return_code == 0:
                logger.info(
                    f"create_ebs_volume(): Successfully provisioning, mounting and formatting of " +
                    f"EBS volume '{volume_id}' of {size} gigabytes, on mount point '{mount_point}'"
                )
                return volume_id
            else:
                logger.error(
                    f"create_ebs_volume(): Failure to complete mounting and formatting of " +
                    f"EBS volume '{volume_id}' on mount point '{mount_point}'"
                )
                return None
        else:
            logger.debug(
                "create_ebs_volume(): 'Dry Run' skipping of the mounting and formatting of " +
                f"EBS volume '{volume_id}' on mount point '{mount_point}'"
            )
            return None

    except Exception as e:
        logger.error(
            f"create_ebs_volume(): EBS volume '{volume_id}' mounting/formatting script exception: {str(e)}"
        )
        return None


def delete_ebs_volume(
        volume_id: str,
        device: str = _SCRATCH_DEVICE,
        mount_point: str = scratch_dir_path(),
        dry_run: bool = False
) -> None:
    """
    Detaches and deletes the previously provisioned specified volume.

    Notes:
    * This operation can only be performed when the application is running inside an EC2 instance

    :param volume_id: identifier of the EBS volume to be deleted
    :param device: EBS device path of volume to be deleted (default: config.yaml designated 'scratch' device name)
    :param mount_point: OS mount point (path) from which to unmount the volume (default: local 'scratch' mount point)
    :param dry_run: no operation test run if True
    """
    if not (volume_id or device or mount_point):
        logger.error(
            "delete_ebs_volume(): empty 'volume_id', 'device' or 'mount_point' argument?"
        )
        return

    # The application can only create an EBS volume if it is running
    # within an EC2 instance so retrieve the EC2 instance identifier
    instance_id = get_ec2_instance_id()
    if not (dry_run or instance_id):
        logger.warning(
            "delete_ebs_volume(): not inside an EC2 instance? Cannot dynamically provision your EBS volume?"
        )
        return

    ec2_region = get_ec2_instance_region()

    # 3.1 (Popen() run sudo umount -d mount_point) - Cleanly unmount EBS volume after it is no longer needed.
    try:
        if not dry_run:
            cmd = f"sudo umount -d {mount_point}"
            logger.debug(cmd)
            with Popen(
                cmd,
                bufsize=1,
                universal_newlines=True,
                stderr=PIPE,
                shell=True
            ) as proc:
                for line in proc.stderr:
                    logger.debug(line)

            if proc.returncode == 0:
                logger.info(
                    "delete_ebs_volume(): Successfully unmounted " +
                    f"EBS volume '{volume_id}' from mount point '{mount_point}'"
                )
            else:
                logger.error(
                    "delete_ebs_volume(): Failure to complete unmounting of " +
                    f"EBS volume '{volume_id}' on mount point '{mount_point}'"
                )
                return
        else:
            logger.debug(
                f"delete_ebs_volume(): 'Dry Run' skipping of the unmounting of " +
                f"EBS volume '{volume_id}' on mount point '{mount_point}'"
            )

    except Exception as e:
        logger.error(f"delete_ebs_volume(): EBS volume '{mount_point}' could not be unmounted? Exception: {str(e)}")

    if dry_run and not volume_id:
        logger.warning(f"delete_ebs_volume(): volume_id is null.. skipping volume detach and deletion")
        return

    volume = ec2_resource(region_name=ec2_region).Volume(volume_id)

    # 3.2 (EC2 client) - Detach the EBS volume on the scratch device from the EC2 instance.
    try:
        vol_detach_response = volume.detach_from_instance(
            Device=device,
            Force=True,
            InstanceId=instance_id,
            DryRun=dry_run

        )
        logger.debug(f"delete_ebs_volume(): volume.detach() response:\n{pp.pformat(vol_detach_response)}")
    except Exception as e:
        logger.error(
            f"delete_ebs_volume(): cannot detach the EBS volume '{volume_id}' from current instance: {str(e)}"
        )
        return

    # 3.3 (EC2 client) - Delete the instance (to avoid incurring further economic cost).
    try:
        del_response = volume.delete(
            DryRun=dry_run
        )
        logger.debug(f"delete_ebs_volume(): successful volume.delete() response:\n{pp.pformat(del_response)}?")
    except Exception as ex:
        logger.error(
            f"delete_ebs_volume(): cannot detach the EBS volume '{volume_id}' from instance, exception: {str(ex)}"
        )
