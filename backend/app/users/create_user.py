"""Trusted local provisioning; passwords are read interactively, never from CLI arguments."""

import argparse
import getpass
import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ApplicationError
from app.core.logging import configure_logging
from app.database.session import dispose_engine, get_session_factory
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an EduMS user through trusted database access")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    arguments = parser.parse_args()
    configure_logging()
    password = getpass.getpass("Password (12–128 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        logger.error("Passwords do not match")
        return 1
    try:
        data = UserCreate(email=arguments.email, full_name=arguments.full_name, role=arguments.role, password=password)
        with get_session_factory()() as session:
            user = UserService(session).create_user(data)
            logger.info("Provisioning complete (user_id=%s)", user.id)
        return 0
    except ValidationError:
        logger.error("Invalid user data; check email, full name, role and password length")
        return 1
    except ApplicationError as exc:
        logger.error("Provisioning failed (%s)", exc.code)
        return 1
    except SQLAlchemyError as exc:
        logger.error("Provisioning failed (%s); check PostgreSQL and migrations", type(exc).__name__)
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
