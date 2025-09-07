import json
import os

# Root socials category
ROOT_CATEGORY = "Socials"

# Action categories
UPDATE_CATEGORY = "_update"
UPDATE_METADATA_CATEGORY = "_metadata"
DELETE_CATEGORY = "_delete"

# Error category root. All error categories sit below this
ERROR_CATEGORY = "__errors"

# Standardise reference to Megabyte
MB_SIZE = 1048576

# Standard bar format for TQDM
desc_length = 20
bar_format = "{desc:<20}{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"secrets.json")) as f:
    secrets = json.load(f)

albums = secrets["albums"]
locations = secrets["locations"]
flickr_secrets = secrets["flickr"]
quantum_secrets = secrets["quantum"]