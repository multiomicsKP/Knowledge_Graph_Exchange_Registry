import logging
from os import getenv
from os.path import expanduser, dirname, abspath
from typing import Dict

import boto3
from botocore.client import Config

import configparser
import yaml

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

# Master flag for local development runs bypassing
# authentication and other production processes
DEV_MODE = getenv('DEV_MODE', default=False)

home = expanduser("~")
AWS_CONFIG_ROOT = home + "/.aws/"

# the following config file should be visible in the 'kgea/server/config' subdirectory, as
# copied from the available template and populated with site-specific configuration values
CONFIG_FILE_PATH = abspath(dirname(__file__) + '/config.yaml')

PROVIDER_METADATA_FILE = 'provider.yaml'
FILE_SET_METADATA_FILE = 'file_set.yaml'
CONTENT_METADATA_FILE = 'content_metadata.json'  # this particular file is expected to be JSON and explicitly named


def validate_session_configuration():
    try:
        with open(AWS_CONFIG_ROOT + 'credentials', 'r') as credentials_file:
            client_credentials = boto3.Session().get_credentials().get_frozen_credentials()

            credentials_config = configparser.ConfigParser()
            credentials_config.read_file(credentials_file)

            try:
                assert (client_credentials.access_key == credentials_config['default']['aws_access_key_id'])
            except AssertionError:
                raise AssertionError("the boto3 client does not have correct aws_access_key_id")

            try:
                assert (client_credentials.secret_key == credentials_config['default']['aws_secret_access_key'])
            except AssertionError:
                raise AssertionError("the boto3 client does not have correct aws_secret_access_key")

    except FileNotFoundError as e:
        print("ERROR: ~/.aws/credentials isn't found! try running `aws configure` after installing `aws-cli`")
        print(e)
        return False
    except AssertionError as e:
        print("ERROR: boto3 s3 client has different configuration information from ~/.aws/credentials!")
        print(e)
        return False
    except KeyError as e:
        print("ERROR: ~/.aws/credentials does not have all the necessary keys")
        print(e)
        return False

    return True


def validate_client_configuration():
    try:
        with open(AWS_CONFIG_ROOT + 'config', 'r') as config_file:
            client_credentials = boto3.client("s3")._client_config
            config = configparser.ConfigParser()
            config.read_file(config_file)

            # if config['default']['region'] != 'us-east-1':
            #     print("NOTE: we recommend using us-east-1 as your region",
            #           "(currently %s)" % config['default']['region'])
            #     # this is a warning, no need to return false

            try:
                assert (client_credentials.region_name == config['default']['region'])
            except AssertionError:
                raise AssertionError("the boto3 client does not have the same region as `~/.aws/config")

    except FileNotFoundError as e:
        print("ERROR: ~/.aws/config isn't found! try running `aws configure` after installing `aws-cli`")
        print(e)
        return False
    except AssertionError as e:
        print("ERROR: boto3 s3 client has different configuration information from ~/.aws/config!")
        print(e)
        return False
    except KeyError as e:
        print("ERROR: ~/.aws/config does not have all the necessary keys")
        print(e)
        return False
    finally:
        return True


s3_client = None

try:
    assert (validate_session_configuration())
    assert (validate_client_configuration())
    s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
except Exception as e:
    print('ERROR: s3 configuration failed to load, kgea may not work properly')
    print(e)

# Exported  'application configuration' dictionary
_app_config: Dict = dict()


def get_app_config() -> dict:
    if not _app_config:
        _load_app_config()
    return _app_config


def _load_app_config() -> dict:
    global _app_config

    try:
        with open(CONFIG_FILE_PATH, mode='r', encoding='utf-8') as app_config_file:

            app_config_raw = yaml.load(app_config_file, Loader=Loader)
            
            if 'aws' not in app_config_raw:
                pass
            else:
                if 'account' not in app_config_raw['aws'] or \
                   'external_id' not in app_config_raw['aws'] or \
                   'iam_role_name'not in app_config_raw['aws']:
                    raise RuntimeError(
                        "Missing mandatory aws 'account', 'external_id' and/or 'iam_role_name' attributes" +
                        " in the '~/kgea/server/config/config.yaml' configuration file."
                    )
                elif 's3' not in app_config_raw['aws'] or \
                     'bucket' not in app_config_raw['aws']['s3'] or \
                     'archive-directory' not in app_config_raw['aws']['s3']:
                    raise RuntimeError(
                        "Missing mandatory aws.s3 'bucket' and/or 'archive-directory' attribute" +
                        " in the '~/kgea/server/config/config.yaml' configuration file."
                    )
            if 'github' not in app_config_raw:
                if DEV_MODE:
                    logging.warning(
                        "Github credentials are missing inside the application config.yaml file?\n" +
                        "These to be set for publication of KGE file set entries to the Translator Registry.\n"
                        "Assume that you don't care... thus, the application will still run (only in DEV_MODE)."
                    )
                else:
                    raise RuntimeError(
                        "Missing 'github.token' attribute in '~/kgea/server/config/config.yaml' configuration file!"
                    )
            if s3_client is not None:
                # TODO: detect the bucket here
                # if not detected, raise an error
                pass

            _app_config = dict(app_config_raw)

            # TODO: Review this: we second guess a sensible Translator site name here
            _app_config.setdefault("site_hostname", "https://kge.translator.ncats.io")

        if DEV_MODE:
            # For the EncryptedCookieStorage() managed
            # Session management during development
            if 'secret_key' not in _app_config:
                import base64
                from cryptography import fernet

                fernet_key = fernet.Fernet.generate_key()
                secret_key = base64.urlsafe_b64decode(fernet_key)
                _app_config['secret_key'] = secret_key

                # persist updated updated _app_config back to config.yaml?
                with open(CONFIG_FILE_PATH, mode='w', encoding='utf-8') as app_config_file:
                    yaml.dump(_app_config, app_config_file, Dumper=Dumper)

        return _app_config

    except Exception as exc:
        raise RuntimeError('KGE Archive resource configuration file failed to load? :' + str(exc))


#############################################################
# Here, we centralize the various application web endpoints #
#############################################################


BACKEND_PATH = 'archive/'
if DEV_MODE:
    # Development Mode for local testing

    # Point to http://localhost:8090 for frontend UI web application endpoints
    FRONTEND = "http://localhost:8090/"

    # Point to http://localhost:8080 for backend archive web service endpoints
    BACKEND = "http://localhost:8080/" + BACKEND_PATH
else:
    # Production NGINX resolves relative paths otherwise?
    FRONTEND = "/"
    BACKEND = FRONTEND + BACKEND_PATH

##################################################
# Frontend Web Service Endpoints - all GET calls #
##################################################

LANDING_PAGE = FRONTEND
HOME_PAGE = FRONTEND + "home"
GRAPH_REGISTRATION_FORM = FRONTEND + "register/graph"
FILESET_REGISTRATION_FORM = FRONTEND + "register/fileset"
METADATA_PAGE = FRONTEND + "metadata"
UPLOAD_FORM = FRONTEND + "upload"
DATA_UNAVAILABLE = FRONTEND + "unavailable"

#################################
# Backend Web Service Endpoints #
#################################

# catalog controller
GET_KNOWLEDGE_GRAPH_CATALOG = BACKEND + "catalog"  # GET
REGISTER_KNOWLEDGE_GRAPH = BACKEND + "register/graph"  # POST
REGISTER_FILESET = BACKEND + "register/fileset"  # POST
PUBLISH_FILE_SET = BACKEND + "publish"  # GET

# upload controller
SETUP_UPLOAD_CONTEXT = BACKEND + "upload"  # GET
UPLOAD_FILE = BACKEND + "upload"  # POST
GET_UPLOAD_STATUS = BACKEND + "upload/progress"  # GET


# content controllers
def _versioned_backend_target_url(kg_id: str, kg_version: str, target: str):
    return BACKEND + kg_id + "/" + kg_version + "/" + target  # GET


def get_fileset_metadata_url(kg_id: str, kg_version: str):
    return _versioned_backend_target_url(kg_id, kg_version, target="metadata")


def get_meta_knowledge_graph_url(kg_id: str, kg_version: str):
    return _versioned_backend_target_url(kg_id, kg_version, target="meta_knowledge_graph")


def get_fileset_download_url(kg_id: str, kg_version: str):
    return _versioned_backend_target_url(kg_id, kg_version, target="download")
