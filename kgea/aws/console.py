#!/usr/bin/env python

from kgea.aws.assume_role import AssumeRole

import requests
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus
import json
import webbrowser

account_id_from_user: str = ""
external_id: str = ""
role_name_from_user: str = ""

# Prompt user for target account ID, ExternalID and name of IAM Role to assume
if len(sys.argv) == 4:
    account_id_from_user = sys.argv[1]
    external_id = sys.argv[2]
    role_name_from_user = sys.argv[3]
else:
    print("Usage: ")
    print(
        "python -m kgea.aws."+Path(sys.argv[0]).stem +
        " <host_account_id> <guest_external_id> <target_iam_role_name>"
    )
    exit(0)


_assumed_role = AssumeRole(
                    host_aws_account_id=account_id_from_user,
                    guest_external_id=external_id,
                    target_role_name=role_name_from_user
                )
        
# Make a request to the AWS federation endpoint to get a sign-in.
#
# token, passing parameters in the query string. The call requires an
# Action parameter ('getSigninToken') and a Session parameter (the
# JSON string that contains the temporary credentials that have
# been URL-encoded).
request_parameters = "?Action=getSigninToken"
request_parameters += "&Session="
request_parameters += quote_plus(_assumed_role.get_credentials_jsons())
request_url = "https://signin.aws.amazon.com/federation"
request_url += request_parameters
r = requests.get(request_url)

# Get the return value from the federation endpoint.
#
# a JSON document that has a single element named 'SigninToken'.
sign_in_token = json.loads(r.text)["SigninToken"]

# Create the URL that will let users sign in to the console using the sign-in token.
# This URL must be used within 15 minutes of when the sign-in token was issued.
request_parameters = "?Action=login"
request_parameters += "&Issuer="
request_parameters += "&Destination="
request_parameters += quote("https://console.aws.amazon.com/")
request_parameters += "&SigninToken=" + sign_in_token
request_url = "https://signin.aws.amazon.com/federation"
request_url += request_parameters

# Use the default browser to sign in to the AWS Dashboard using the generated URL.
webbrowser.open(request_url)
