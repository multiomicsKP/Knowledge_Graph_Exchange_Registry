"""
Knowledge Graph Archive back end Web Services component
"""
from os import path
import connexion
from connexion.apps import aiohttp_app
import aiohttp_cors

from kgea.server.web_services.catalog import KnowledgeGraphCatalog
from kgea.server.web_services.kgea_session import KgeaSession
import logging

aiohttp_app.logger = logging.getLogger(__name__)


def main():
    """
    KGE Archive Web Services application entry point
    """
    options = {
        "swagger_ui": True
    }
    specification_dir = path.join(path.dirname(__file__), 'openapi')
    app = connexion.AioHttpApp(
        __name__,
        specification_dir=specification_dir,
        options=options,
        server_args={
            "client_max_size": 256*1024**3
        }
    )
    
    app.add_api('openapi.yaml',
                arguments={
                    'title': 'OpenAPI for the Biomedical Translator Knowledge Graph EXchange Archive. ' +
                             'Although this API is SmartAPI compliant, it will not normally be visible in the ' +
                             'Translator SmartAPI Registry since it is mainly meant to be accessed through ' +
                             'Registry indexed KGE File Sets, which will have distinct entries in the Registry.'
                },
                pythonic_params=True,
                pass_context_arg_name='request')

    # See https://github.com/aio-libs/aiohttp-cors#usage

    # Enable CORS for all origins.
    cors = aiohttp_cors.setup(app.app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    
    # Register all routers for CORS.
    for route in list(app.app.router.routes()):
        cors.add(route)

    KgeaSession.initialize(app.app)

    app.run(
        port=8080,
        server="aiohttp",
        use_default_access_log=True
    )

    KgeaSession.close_global_session()
