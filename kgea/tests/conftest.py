import logging
import pytest
import os

import connexion


@pytest.fixture
def client(loop, aiohttp_client):
    """

    :param loop:
    :param aiohttp_client:
    :return:
    """
    logging.getLogger('connexion.operation').setLevel('ERROR')
    options = {
        "swagger_ui": True
        }
    specification_dir = os.path.join(os.path.dirname(__file__), '../kgea/server',
                                     'web_services',
                                     'openapi')
    app = connexion.AioHttpApp(__name__, specification_dir=specification_dir,
                               options=options)
    app.add_api('openapi.yaml', pythonic_params=True,
                pass_context_arg_name='request')
    return loop.run_until_complete(aiohttp_client(app.app))
