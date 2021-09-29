#!/usr/bin/env python
"""
This CLI script will take  host AWS account id, guest external id and
the name of a host account IAM role, to obtain temporary AWS service
credentials to execute an AWS Secure Token Service-mediated access
to a Simple Storage Service (S3) bucket given as an argument.
"""
import sys
from typing import List, Union
from os import remove, pipe
from pathlib import Path
from pprint import PrettyPrinter

from botocore.config import Config

from kgea.aws.assume_role import AssumeRole, aws_config

pp = PrettyPrinter(indent=4)


def usage(err_msg: str = ''):
    """

    :param err_msg:
    """
    if err_msg:
        print(err_msg)

    print("Usage:\n")
    print(
        "\tpython -m kgea.aws."+Path(sys.argv[0]).stem +
        " <operation> [<object_key>+|<prefix_filter>]\n\n" +
        "where <operation> is one of upload, list, copy, download, delete, delete-batch and test.\n\n"
        "Note:\tone or more <object_key> strings are only required for 'delete' operation.\n" +
        "\tA <prefix_filter> string is only required for 'delete-batch' operation.\n"
    )
    exit(0)


s3_bucket_name: str = aws_config["s3"]["bucket"]
s3_region_name: str = aws_config["s3"]["region"]

assumed_role = AssumeRole()

s3_client = \
    assumed_role.get_client(
        's3',
        config=Config(
            signature_version='s3v4',
            region_name=s3_region_name
        )
    )


def upload_file(
        bucket_name: str,
        source_file,
        target_object_key: str,
        client=s3_client
):
    """
    Upload a file.
    
    :param bucket_name:
    :param source_file: may be a file name string or a file descriptor open for reading
    :param target_object_key:
    :param client:
    :return:
    """
    if isinstance(source_file, str):
        print(
            f"\n###Uploading file '{source_file}' to object " +
            f"'{target_object_key}' in the S3 bucket '{bucket_name}'\n"
        )
        try:
            client.upload_file(source_file, bucket_name, target_object_key)
        except Exception as exc:
            usage("upload_file(): 'client.upload_file' exception: " + str(exc))
    else:
        # assume that an open file descriptor is being passed for reading
        print(
            f"\n###Uploading file '{source_file.name}' to object " +
            f"'{target_object_key}' in the S3 bucket '{bucket_name}'\n"
        )
        try:
            client.upload_fileobj(source_file, bucket_name, target_object_key)
        except Exception as exc:
            usage("upload_file(): 'client.upload_fileobj' exception: " + str(exc))


def get_object_keys(
        bucket_name: str,
        filter_prefix='',
        client=s3_client
) -> List[str]:
    """
    Check for the new file in the bucket listing.
    :param client:
    :param bucket_name:
    :param filter_prefix:
    :return:
    """
    response = client.list_objects_v2(Bucket=bucket_name, Prefix=filter_prefix)

    if 'Contents' in response:
        print("### Returning list of keys with prefix '" + filter_prefix +
              "'from the S3 bucket '" + bucket_name + "'")
        return [item['Key'] for item in response['Contents']]
    else:
        print("S3 bucket '" + bucket_name + "' is empty?")
        return []


def list_files(
        bucket_name: str,
        client=s3_client
):
    """
    Check for the new file in the bucket listing.
    :param client:
    :param bucket_name:
    :return:
    """
    response = client.list_objects_v2(Bucket=bucket_name)
    
    if 'Contents' in response:
        print("### Listing contents of the S3 bucket '" + bucket_name + "':")
        for entry in response['Contents']:
            print(entry['Key'], ':', entry['Size'])
    else:
        usage("S3 bucket '" + bucket_name + "' is empty?")


def download_file(
        bucket_name: str,
        source_object_key: str,
        target_file=None,
        client=s3_client
) -> str:
    """
    Delete an object key (file) in a given bucket.

    :param client: S3 client to access S3 bucket
    :param bucket_name: the target bucket
    :param source_object_key: the target object_key
    :param target_file: file name string or file descriptor (open for (binary) writing) to which to save the file
    :return:
    """
    if not target_file:
        target_file = source_object_key.split("/")[-1]
        
    if isinstance(target_file, str):
        print(
            f"\n###Downloading file '{target_file}' from object " +
            f"'{source_object_key}' in the S3 bucket '{bucket_name}'\n"
        )
        try:
            client.download_file(Bucket=bucket_name, Key=source_object_key, Filename=target_file)
        except Exception as exc:
            usage("download_file(): 'client.download_file' exception: " + str(exc))
    else:
        # assume that an open file descriptor is being passed for reading
        print(
            f"\n###Downloading file '{target_file.name}' from object " +
            f"'{source_object_key}' in the S3 bucket '{bucket_name}'\n"
        )
        try:
            client.download_fileobj(Bucket=bucket_name, Key=source_object_key, Fileobj=target_file)
        except Exception as exc:
            usage("upload_file(): 'client.downloadload_fileobj' exception: " + str(exc))
    
    return target_file


def local_copy(
        source_key: str,
        target_key: str,
        bucket: str = s3_bucket_name,
        client=s3_client,
):
    """

    :param source_key:
    :param target_key:
    :param bucket:
    :param client:
    """
    copy_source = {
        'Bucket': bucket,
        'Key': source_key
    }
    client.copy(
        CopySource=copy_source,
        Bucket=bucket,
        Key=target_key
    )


# So-called 'remote' copy relies on deferential
# target_client configuration (by the caller)
# and uses a locally cached file for the copy operation
# (presumed fast enough on an EC2 instance?)
def remote_copy(
        source_key: str,
        target_key: str,
        target_bucket: str,
        target_client,
        source_bucket=s3_bucket_name,
        source_client=s3_client,
):
    """
    Copy an object from a source bucket and account to a second bucket and account, where access
    to the account is defined in the target client configuration by the caller of the function.
    
    :param source_key:
    :param target_key:
    :param source_bucket:
    :param target_bucket:
    :param source_client:
    :param target_client:
    """
    if not (target_bucket and target_client):
        usage("Remote copy: requires an non-empty target_bucket and target_client")

    # TODO: can this be converted to a Unix file PIPE operation?
    #============================================
    # Python program to explain os.pipe() method

    # importing os module
    import os

    # Create a pipe
    r, w = os.pipe()

    # The returned file descriptor r and w
    # can be used for reading and
    # writing respectively.

    # We will create a child process
    # and using these file descriptor
    # the parent process will write
    # some text and child process will
    # read the text written by the parent process

    # Create a child process
    pid = os.fork()

    # pid greater than 0 represents
    # the parent process
    if pid > 0:
    
        # This is the parent process
        # Closes file descriptor r
        os.close(r)
    
        # Write some text to file descriptor w
        print("Parent process is writing")
        text = b"Hello child process"
        os.write(w, text)
        print("Written text:", text.decode())


    else:
    
        # This is the parent process
        # Closes file descriptor w
        os.close(w)
    
        # Read the text written by parent process
        print("\nChild Process is reading")
        r = os.fdopen(r)
        print("Read text:", r.read())
    #============================================
    source_file_name = download_file(
                            bucket_name=source_bucket,
                            source_object_key=source_key,
                            client=source_client
                        )
    upload_file(
            bucket_name=target_bucket,
            source_filepath=source_file_name,
            target_object_key=target_key,
            client=target_client
    )
    
    # Need to delete the locally cached file here,
    # unless one streams the data in a PIPE
    remove(source_file_name)


def delete_object(
        bucket_name: str,
        target_object_key: str,
        client=s3_client
):
    """
    Delete an object key (file) in a given bucket.
    
    :param client:
    :param bucket_name:
    :param target_object_key:
    :return:
    """
    # print(
    #     "\n### Deleting the test object '" + object_key +
    #     "' in the S3 bucket '" + bucket_name + "'"
    # )
    response = client.delete_object(Bucket=bucket_name, Key=target_object_key)
    deleted = response["DeleteMarker"]
    if deleted:
        print(f"'{target_object_key}' deleted in bucket '{bucket_name}'!")
    else:
        print(f"Could not delete the '{target_object_key}' in bucket '{bucket_name}'?")


# Run the module as a CLI
if __name__ == '__main__':

    s3_operation: str = ''
    
    if len(sys.argv) > 1:

        s3_operation = sys.argv[1]
        
        if s3_operation.lower() == 'help':
            usage()
    
        elif s3_operation.lower() == 'upload':
            if len(sys.argv) >= 3:
                filepath = sys.argv[2]
                object_key = sys.argv[3] if len(sys.argv) >= 4 else filepath
                upload_file(s3_bucket_name, filepath, object_key)
            else:
                usage("\nMissing path to file to upload?")

        elif s3_operation.lower() == 'list':
            list_files(s3_bucket_name)

        elif s3_operation.lower() == 'copy':
            
            if len(sys.argv) >= 4:
                
                source_key = sys.argv[2]
                target_key = sys.argv[3]
                target_s3_bucket_name = s3_bucket_name

                # Default target bucket may also be overridden on the command line
                target_s3_bucket_name = sys.argv[4] if len(sys.argv) >= 5 else target_s3_bucket_name
                
                local_copy(
                    source_key=source_key,
                    target_key=target_key,
                )
            else:
                usage("\nLocal copy() operation needs a 'source' and 'target' key?")

        elif s3_operation.lower() == 'remote-copy':
    
            if len(sys.argv) >= 4:
        
                source_key = sys.argv[2]
                target_key = sys.argv[3]
        
                #
                # The 'target' client and possibly, the target bucket
                # (if not given as the 3rd CLI arguments after the 'copy' command)
                # are configured here using "s3_remote" settings as provided
                # from the application's config.yaml file.
                #
                target_client = None
                target_s3_bucket_name = None
            
                if "s3_remote" not in aws_config or \
                    not all(
                        [
                            tag in aws_config["s3_remote"]
                            for tag in [
                                'guest_external_id',
                                'host_account',
                                'iam_role_name',
                                'archive-directory',
                                'bucket',
                                'region'
                            ]
                        ]):
                    usage("Remote copy(): 's3_remote' settings in 'config.yaml' missing or incomplete?")
            
                    target_assumed_role = AssumeRole(
                        host_account=aws_config["s3_remote"]['host_account'],
                        guest_external_id=aws_config["s3_remote"]['guest_external_id'],
                        iam_role_name=aws_config["s3_remote"]['iam_role_name']
                    )
            
                    target_client = \
                        target_assumed_role.get_client(
                            's3',
                            config=Config(
                                signature_version='s3v4',
                                region_name=aws_config["s3_remote"]["region"]
                            )
                        )
                    
                    assert target_client
                    
                    target_s3_bucket_name = aws_config["s3_remote"]["bucket"]
        
                # Default remote target bucket name may also be overridden on the command line
                target_s3_bucket_name = sys.argv[4] if len(sys.argv) >= 5 else target_s3_bucket_name
        
                if not target_s3_bucket_name:
                    usage("Remote copy(): missing target bucket name?")
                
                remote_copy(
                    source_key=source_key,
                    target_key=target_key,
                    source_bucket=s3_bucket_name,
                    target_bucket=target_s3_bucket_name,
                    source_client=s3_client,
                    target_client=target_client
                )
            else:
                usage("\nRemote copy(): operation needs a 'source' and 'target' key?")

        elif s3_operation.lower() == 'download':
            if len(sys.argv) >= 3:
                object_key = sys.argv[2]
                filename = sys.argv[3] if len(sys.argv) >= 4 else object_key.split("/")[-1]
                download_file(
                    bucket_name=s3_bucket_name,
                    source_object_key=object_key,
                    target_filename=filename
                )
            else:
                usage("\nMissing S3 object key for file to download?")
        
        elif s3_operation.lower() == 'delete':
            if len(sys.argv) >= 3:
                object_keys = sys.argv[2:]
                for key in object_keys:
                    print("\t" + key)
                prompt = input("Proceed (Type 'yes')? ")
                if prompt.upper() == "YES":
                    for key in object_keys:
                        delete_object(s3_bucket_name, key)
                else:
                    print("Cancelling deletion of objects...")
            else:
                usage("\nMissing S3 key(s) of object(s) to delete?")

        elif s3_operation.lower() == 'delete-batch':
            if len(sys.argv) >= 3:
                object_keys = get_object_keys(s3_bucket_name, filter_prefix=sys.argv[2])
                print("Deleting key(s): ")
                for key in object_keys:
                    print("\t"+key)
                prompt = input("Proceed (Type 'yes')? ")
                if prompt.upper() == "YES":
                    for key in object_keys:
                        delete_object(s3_bucket_name, key)
                else:
                    print("Cancelling deletion of objects...")
            else:
                usage("\nMissing prefix filter for keys of S3 object(s) to delete?")
        else:
            usage("\nUnknown s3_operation: '" + s3_operation + "'")
    else:
        usage()
