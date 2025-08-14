#!/usr/bin/python
from semanticscholar_lib import *
import json
import sys

print(json.dumps(get_semantic_scholar_id_from_title(sys.argv[1]), indent=2))

print(json.dumps(get_url_from_title(sys.argv[1]), indent=2))

