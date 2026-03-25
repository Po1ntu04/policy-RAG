"""Authentication mechanism for the API.

Define a simple mechanism to authenticate requests.
More complex authentication mechanisms can be defined here, and be placed in the
`authenticated` method (being a 'bean' injected in fastapi routers).

Authorization can also be made after the authentication, and depends on
the authentication. Authorization should not be implemented in this file.

Authorization can be done by following fastapi's guides:
* https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/
* https://fastapi.tiangolo.com/tutorial/security/
* https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/
"""

# mypy: ignore-errors
# Disabled mypy error: All conditional function variants must have identical signatures
# We are changing the implementation of the authenticated method, based on
# the config. If the auth is not enabled, we are not defining the complex method
# with its dependencies.
import logging
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from private_gpt.settings.settings import settings
from private_gpt.server.auth.token import verify_token

# 401 signify that the request requires authentication.
# 403 signify that the authenticated user is not authorized to perform the operation.
NOT_AUTHENTICATED = HTTPException(
    status_code=401,
    detail="Not authenticated",
    headers={"WWW-Authenticate": 'Basic realm="All the API", charset="UTF-8"'},
)

logger = logging.getLogger(__name__)


def _simple_authentication(authorization: Annotated[str, Header()] = "") -> bool:
    """Check if the request is authenticated."""
    if not authorization:
        return False
    if authorization.startswith("Bearer "):
        return False
    if not secrets.compare_digest(authorization, settings().server.auth.secret):
        raise NOT_AUTHENTICATED
    return True


if not settings().server.auth.enabled:
    logger.debug(
        "Defining a dummy authentication mechanism for fastapi, always authenticating requests"
    )

    # Define a dummy authentication method that always returns True.
    def authenticated() -> bool:
        """Check if the request is authenticated."""
        return True

else:
    logger.info("Defining the given authentication mechanism for the API")

    # Method to be used as a dependency to check if the request is authenticated.
    def authenticated(
        request: Request,
        authorization: Annotated[str, Header()] = "",
        _simple_authentication: Annotated[bool, Depends(_simple_authentication)] = False,
    ) -> bool:
        """Check if the request is authenticated."""
        assert settings().server.auth.enabled
        if authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "", 1).strip()
            payload = verify_token(token, settings().server.auth.secret)
            if not payload:
                raise NOT_AUTHENTICATED
            request.state.user = payload
            return True
        if _simple_authentication:
            return True
        raise NOT_AUTHENTICATED
