"""
KGE Archive Back End Web Services Handlers
"""
from typing import List, Dict
from os import getenv
import logging

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from aiohttp import web
import aiohttp_jinja2

from aiohttp_session import get_session

from kgea.config import (
    get_app_config,
    
    LANDING_PAGE,
    HOME_PAGE,
    GET_KNOWLEDGE_GRAPH_CATALOG,
    REGISTER_KNOWLEDGE_GRAPH,
    REGISTER_FILESET,
    METADATA_PAGE,
    FILESET_REGISTRATION_FORM,
    PUBLISH_FILE_SET,
    # SETUP_UPLOAD_CONTEXT,
    UPLOAD_FILE,
    DIRECT_URL_TRANSFER,
    CANCEL_UPLOAD,
    # GET_UPLOAD_STATUS,
    get_fileset_metadata_url,
    get_meta_knowledge_graph_url,
    BACKEND
)
from kgea.server.web_services.catalog import get_biolink_model_releases
from kgea.server.web_services.kgea_session import (
    initialize_user_session,
    user_permitted,
    redirect,
    with_session,
    report_bad_request
)
from kgea.server.web_services.kgea_user_roles import (
    KGE_USER_ROLE,
    DEFAULT_KGE_USER_ROLE
)
from .kgea_users import (
    login_url,
    logout_url,
    authenticate_user,
    mock_user_attributes
)
from kgea.server.web_services.kgea_file_ops import get_default_date_stamp, get_fileset_versions_available

# Master flag for local development runs bypassing authentication and other production processes
DEV_MODE = getenv('DEV_MODE', default=False)

logger = logging.getLogger(__name__)
logger.setLevel('DEBUG')

# Opaquely access the configuration dictionary
_KGEA_APP_CONFIG = get_app_config()


#############################################################
# Controller Handlers
#
# Insert imports and return calls into into web_ui/__init__.py:
#
# from .kgea_ui_handlers import (
#     kge_landing_page,
#     kge_login,
#     kge_client_authentication,
#     get_kge_home,
#     kge_logout,
#     get_kge_graph_registration_form,
#     get_kge_fileset_registration_form,
#     get_kge_file_upload_form
# )
#############################################################


async def kge_landing_page(request: web.Request) -> web.Response:
    """Display landing page.

    :param request:
    :type request: web.Request

    :rtype: login web.Response login page or redirect to authenticated /home page
    """
    session = await get_session(request)
    if not session.empty:
        # if active session and no exception raised, then
        # redirect to the home page, with a session cookie
        await redirect(request, HOME_PAGE, active_session=True)
    else:
        # Session is not active, then render the login page
        response = aiohttp_jinja2.render_template('login.html', request=request, context={})
        return response


async def get_kge_home(request: web.Request) -> web.Response:
    """Get default landing page

    :param request:
    :type request: web.Request

    :rtype: web.Response
    """
    session = await get_session(request)
    if not session.empty:
        context = {
            "submitter_name": session['name'],
            "user_role": session.get('user_role') if 'user_role' in session else DEFAULT_KGE_USER_ROLE,
            "get_catalog": GET_KNOWLEDGE_GRAPH_CATALOG,
            "backend": BACKEND,
            "metadata_page": METADATA_PAGE,
            "fileset_registration_form": FILESET_REGISTRATION_FORM,
        }

        logger.debug(f"get_kge_home(): user_role is set to '{context['user_role']}'")

        response = aiohttp_jinja2.render_template('home.html', request=request, context=context)
        return await with_session(request, response)
    else:
        # If session is not active, then just a await redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def kge_client_authentication(request: web.Request):
    """Process client authentication
    :param request:
    :type request: web.Request
    """
    error = request.query.get('error', default='')
    if error:
        error_description = request.query.get('error_description', default='')
        await report_bad_request(request, "User not authenticated. Reason: " + str(error_description))

    code = request.query.get('code', default='')
    state = request.query.get('state', default='')

    if not (code and state):
        await report_bad_request(request, "User not authenticated. Reason: no authorization code returned?")

    user_attributes: Dict = await authenticate_user(code, state)
    
    if user_attributes:

        logger.debug(
            f"kge_client_authentication(): user_attributes are:\n" +
            f"\t\tusername: {str(user_attributes['username'])}\n" +
            f"\t\tname: {str(user_attributes['given_name'])} {str(user_attributes['family_name'])}\n" +
            f"\t\temail: {str(user_attributes['email'])}\n" +
            f"\t\trole: {str(user_attributes[KGE_USER_ROLE])}\n"
        )

        await initialize_user_session(request, user_attributes=user_attributes)
        
        # if active session and no exception raised, then
        # redirect to the home page, with a session cookie
        await redirect(request, HOME_PAGE, active_session=True)
    else:
        # If authentication conditions are not met, then
        # simply redirect back to public landing page
        await redirect(request, LANDING_PAGE)


async def kge_login(request: web.Request):
    """Process client user login
    :param request:
    :type request: web.Request
    """
    # DEV_MODE workaround by-passes full external authentication
    if DEV_MODE:
        # Stub implementation of user_attributes, to fake authentication
        user_attributes: Dict = mock_user_attributes()

        await initialize_user_session(request, user_attributes=user_attributes)

        # then redirects to an authenticated home page
        await redirect(request, HOME_PAGE, active_session=True)

    await redirect(request, login_url())


async def kge_logout(request: web.Request):
    """Process client user logout_url

    :param request:
    :type request: web.Request
    """
    session = await get_session(request)
    if not session.empty:

        session.invalidate()
        
        if DEV_MODE:
            # Just bypass the AWS Cognito and directly redirect to
            # the unauthenticated landing page after session deletion
            await redirect(request, LANDING_PAGE)
        else:
            await redirect(request, logout_url())
    else:
        # If session is not active, then just a await redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def get_kge_graph_registration_form(request: web.Request) -> web.Response:
    """Get web form for specifying KGE Knowledge Graph metadata

    :param request:
    :type request: web.Request

    :rtype: web.Response
    """
    session = await get_session(request)
    if user_permitted(session):
        context = {
            "submitter_name": session['name'],
            "submitter_email": session['email'],
            "registration_action": REGISTER_KNOWLEDGE_GRAPH
        }
        response = aiohttp_jinja2.render_template('graph.html', request=request, context=context)
        return await with_session(request, response)
    else:
        # If session is not active, then just a redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def view_kge_metadata(request: web.Request) -> web.Response:
    """View Metadata for Versioned KGE File Set Metadata

    :param request:
    :type request: web.Request

    :rtype: web.Response
    """
    session = await get_session(request)
    if not session.empty:
        
        kg_id = request.query.get('kg_id', default='')
        if not kg_id:
            await redirect(request, HOME_PAGE, active_session=True)

        fileset_version = request.query.get('fileset_version', default='')
        kg_name = request.query.get('kg_name', default='')

        context = {
            "kg_id": kg_id,
            "kg_name": kg_name,
            "fileset_version": fileset_version,
            "get_fileset_metadata": get_fileset_metadata_url(kg_id, fileset_version),
            "meta_knowledge_graph": get_meta_knowledge_graph_url(kg_id, fileset_version)
        }
        response = aiohttp_jinja2.render_template('metadata.html', request=request, context=context)
        return await with_session(request, response)


#  Look up available Biolink Model  (SemVer) releases
_biolink_model_releases = get_biolink_model_releases()


async def get_kge_fileset_registration_form(request: web.Request) -> web.Response:
    """Get web form for specifying Versioned KGE File Set Metadata

    :param request:
    :type request: web.Request

    :rtype: web.Response
    """
    session = await get_session(request)
    if user_permitted(session):
        
        kg_id = request.query.get('kg_id', default='')
        kg_name = request.query.get('kg_name', default='')

        if not kg_id:
            await redirect(request, HOME_PAGE, active_session=True)

        fileset_versions = get_fileset_versions_available(
            bucket_name=_KGEA_APP_CONFIG['aws']['s3']['bucket']
        )
        # default case when a registered graph has no file versions
        max_major, max_minor = 1, 0
        if kg_id in fileset_versions and len(fileset_versions[kg_id]) > 0:  # if a registered graph does have file versions, increment from latest
            maximum_version = max(float(el) for el in fileset_versions[kg_id])
            max_major_str, max_minor_str = str(maximum_version).split('.')     # because "1.0" splits into ["1", "0"], and can be destructed
            max_major, max_minor = int(max_major_str), int(max_minor_str) + 1  # increment minor version to prevent collision

        context = {
            "kg_id": kg_id,
            "kg_name": kg_name,

            "submitter_name": session['name'],
            "submitter_email": session['email'],

            "biolink_model_releases": _biolink_model_releases,
            "fileset_major_version": max_major,
            "fileset_minor_version": max_minor,

            "date_stamp": get_default_date_stamp(),
            
            "registration_action": REGISTER_FILESET
        }
        response = aiohttp_jinja2.render_template('fileset.html', request=request, context=context)
        return await with_session(request, response)
    else:
        # If session is not active, then just a redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def get_kge_file_upload_form(request: web.Request) -> web.Response:
    """Get web form for specifying KGE File Set upload

    :param request:
    :type request: web.Request
    """
    session = await get_session(request)
    if user_permitted(session):

        submitter_name = session['name']

        kg_id = request.query.get('kg_id', default='')
        kg_name = request.query.get('kg_name', default='')
        fileset_version = request.query.get('fileset_version', default='')

        missing: List[str] = []
        if not kg_id:
            missing.append("kg_id")
        if not kg_name:
            missing.append("kg_name")
        if not fileset_version:
            missing.append("fileset_version")

        if missing:
            await report_bad_request(request, "get_kge_file_upload_form() - missing parameter(s): " + ", ".join(missing))
        
        context = {
            "kg_id": kg_id,
            "kg_name": kg_name,
            "fileset_version": fileset_version,
            "submitter_name": submitter_name,
            "upload_action": UPLOAD_FILE,
            "direct_url_transfer_action": DIRECT_URL_TRANSFER,
            "cancel_upload_action": CANCEL_UPLOAD,
            "publish_file_set_action": PUBLISH_FILE_SET
        }
        response = aiohttp_jinja2.render_template('upload.html', request=request, context=context)
        return await with_session(request, response)

    else:
        # If session is not active, then just a redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def get_kge_fileset_submitted(request: web.Request) -> web.Response:
    """File set submission confirmation page

    :param request:
    :type request: web.Request
    """
    session = await get_session(request)
    if user_permitted(session):
        
        submitter_name = session['name']
        kg_name = request.query.get('kg_name', default='')
        fileset_version = request.query.get('fileset_version', default='')
        
        context = {
            "kg_name": kg_name,
            "fileset_version": fileset_version,
            "submitter_name": submitter_name
        }
        response = aiohttp_jinja2.render_template('submitted.html', request=request, context=context)
        return await with_session(request, response)
    else:
        # If session is not active, then just a await redirect
        # directly back to unauthenticated landing page
        await redirect(request, LANDING_PAGE)


async def get_kge_data_unavailable(request: web.Request) -> web.Response:
    """Data unavailable notification page

    :param request:
    :type request: web.Request
    """
    session = await get_session(request)
    if not session.empty:

        submitter_name = session['name']

        kg_name = request.query.get('kg_name', default='')
        data_type = request.query.get('data_type', default='')
        fileset_version = request.query.get('fileset_version', default='')

        missing: List[str] = []
        if not kg_name:
            missing.append("kg_name")
        if not fileset_version:
            missing.append("fileset_version")
        if missing:
            await report_bad_request(request, "get_kge_file_upload_form() - missing parameter(s): " + ", ".join(missing))
            
        context = {
            "kg_name": kg_name,
            "fileset_version": fileset_version,
            "data_type": data_type,
            "submitter_name": submitter_name
        }
        response = aiohttp_jinja2.render_template('data_unavailable.html', request=request, context=context)
        return await with_session(request, response)
