from os import getenv

# Custom Attribute Keys as constants
KGE_USER_TEAM = "custom:Team"
KGE_USER_AFFILIATION = "custom:Affiliation"
KGE_USER_CONTACT_PI = "custom:Contact PI"
KGE_USER_ROLE = "custom:KGE User Role"

DEFAULT_KGE_USER_ROLE = int(getenv('DEFAULT_KGE_USER_ROLE', default=0))
