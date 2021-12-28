#!/usr/bin/env python
#
# This CLI script will take  host AWS account id, guest external id and
# the name of a host account IAM role, to obtain temporary AWS service
# credentials to execute an AWS Secure Token Service-mediated access
# to the AWS Cognito (OAuth2) management service.
#
from sys import argv
from typing import Dict, List
from pprint import PrettyPrinter

from boto3.exceptions import Boto3Error

from kgea.aws import Help
from kgea.aws.assume_role import AssumeRole, aws_config

import logging
logger = logging.getLogger(__name__)

pp = PrettyPrinter(indent=4)

# Cognito CLI commands
CREATE_USER = "create-user"
GET_USER_DETAILS = "get-user-details"
SET_USER_ATTRIBUTE = "set-user-attribute"  # including disabling
DELETE_USER = "delete-user"

helpdoc = Help(
    default_usage="where <operation> is one of " +
                  f"'{CREATE_USER}', '{GET_USER_DETAILS}', '{SET_USER_ATTRIBUTE}' or '{DELETE_USER}'\n"
)

TEST_USER_NAME = "cognito-test-user"
TEST_TEMP_PASSWORD = "KGE@_Te5t_U$er#1"
TEST_USER_ATTRIBUTES = {
    "email": "richard.bruskiewich@cropinformatics.com",
    "family_name": "Lator",
    "given_name": "Trans",
    "email_verified": "true",
    "website": "https://ncats.nih.gov",
    "custom:Team": "SRI",
    "custom:Affiliation": "NCATS",
    "custom:Contact_PI": "da Boss",
    "custom:User_Role": "2"  # give this bloke editorial privileges
}


def create_user(
    client,
    upi: str,
    uid: str,
    tpw: str,
    attributes: Dict[str, str]
):
    """

    :param client:
    :param upi:
    :param uid:
    :param tpw: temporary password, 15 characters, with at least one upper, lower, number and symbol
    :param attributes: Dict
    """
    user_attributes: List[Dict[str, str]] = list()
    for n, v in attributes.items():
        user_attributes.append(
            {
                "Name": n,
                "Value": v
            }
        )

    try:
        response = client.admin_create_user(
            UserPoolId=upi,
            Username=uid,
            UserAttributes=user_attributes,
            TemporaryPassword=tpw,
            MessageAction='SUPPRESS',
            DesiredDeliveryMediums=['EMAIL'],
        )
        logger.info(f"create_user() response:")
        pp.pprint(response)

    except Boto3Error as b3e:
        logger.error(f"create_user() exception: {b3e}")


def test_create_user():
    upi: str = aws_config["cognito"]["user-pool-id"]
    role = AssumeRole()
    client = role.get_client('cognito-idp')
    create_user(
        client=client,
        upi=upi,
        uid=TEST_USER_NAME,
        tpw=TEST_TEMP_PASSWORD,
        attributes=TEST_USER_ATTRIBUTES
    )


def get_user_details(
        client,
        upi: str,
        uid: str
):
    """

    :param client:
    :param upi:
    :param uid:
    """
    try:
        response = client.admin_get_user(
            UserPoolId=upi,
            Username=uid
        )
        logger.info(f"get_user_details() response:")
        pp.pprint(response)

    except Boto3Error as b3e:
        logger.error(f"get_user_details() exception: {b3e}")


def update_user_attributes(
        client,
        upi: str,
        uid: str,
        attributes: Dict
):
    """

    :param client:
    :param upi:
    :param uid:
    :param attributes:
    """
    try:
        response = client.admin_update_user_attributes(
            UserPoolId=upi,
            Username=uid,
            UserAttributes=[
                {'Name': key, 'Value': value}
                for key, value in attributes.items()
            ],
        )
        logger.info(f"update_user_attributes() response:")
        pp.pprint(response)

    except Boto3Error as b3e:
        logger.error(f"update_user_attributes() exception: {b3e}")


def delete_user(
    client,
    upi: str,
    uid: str
):
    """
    Delete the user with  the given username ('uid')
    :param client: Cognito IDP client handle
    :param upi: user pool within which the user exists
    :param uid: username to delete
    """
    try:
        response = client.admin_delete_user(
            UserPoolId=upi,
            Username=uid
        )
        logger.info(f"delete_user() response:")
        # pp.pprint(response)

    except Boto3Error as b3e:
        logger.error(f"delete_user() exception: {b3e}")


def test_delete_user():
    upi: str = aws_config["cognito"]["user-pool-id"]
    role = AssumeRole()
    client = role.get_client('cognito-idp')
    delete_user(
        client=client,
        upi=upi,
        uid=TEST_USER_NAME
    )


# Run the module as a CLI
if __name__ == '__main__':

    if len(argv) > 1:

        user_pool_id: str = aws_config["cognito"]["user-pool-id"]

        operation = argv[1]

        assumed_role = AssumeRole()

        cognito_client = assumed_role.get_client('cognito-idp')

        if operation.lower() == CREATE_USER:

            if len(argv) >= 3:

                username = argv[2]

                create_user(
                    cognito_client,
                    upi=user_pool_id,
                    uid=username,
                    attributes=dict()
                )
            else:
                helpdoc.usage(
                    err_msg=f"{CREATE_USER} needs the target username",
                    command=CREATE_USER,
                    args={
                        "<username>": 'user account'
                    }
                )
        elif operation.lower() == GET_USER_DETAILS:

            if len(argv) >= 3:

                username = argv[2]

                get_user_details(
                    cognito_client,
                    upi=user_pool_id,
                    uid=username
                )
            else:
                helpdoc.usage(
                    err_msg=f"{GET_USER_DETAILS} needs the target username",
                    command=GET_USER_DETAILS,
                    args={
                        "<username>": 'user account'
                    }
                )
        elif operation.lower() == SET_USER_ATTRIBUTE:

            if len(argv) >= 5:

                username = argv[2]
                name = argv[3]
                value = argv[4]

                user_attributes = {name: value}

                update_user_attributes(
                    cognito_client,
                    upi=user_pool_id,
                    uid=username,
                    attributes=user_attributes
                )
            else:
                helpdoc.usage(
                    err_msg=f"{SET_USER_ATTRIBUTE} needs more arguments",
                    command=SET_USER_ATTRIBUTE,
                    args={
                        "<username>": 'user account',
                        "<name>": "attribute 'name'",
                        "<value>": "attribute 'value'"
                    }
                )
        elif operation.lower() == DELETE_USER:

            if len(argv) >= 3:

                username = argv[2]
                prompt = input(f"\nWarning: deleting user name '{username}' in user pool '{user_pool_id}'? (Type 'delete' again to proceed) ")
                if prompt.upper() == "DELETE":
                    delete_user(
                        client=cognito_client,
                        upi=user_pool_id,
                        uid=username
                    )
                    print(f"\nUser '{username}' successfully deleted!\n")
                else:
                    print("\nCancelling deletion of user...\n")
            else:
                helpdoc.usage(
                    err_msg=f"{DELETE_USER} needs more arguments",
                    command=DELETE_USER,
                    args={
                        "<username>": 'user account'
                    }
                )
        # elif operation.upper() == 'OTHER':
        #     pass
        else:
            helpdoc.usage("\nUnknown Operation: '" + operation + "'")
    else:
        helpdoc.usage()
