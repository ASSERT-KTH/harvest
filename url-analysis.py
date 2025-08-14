#!/usr/bin/python3

import harvest
import sys

d = harvest.collect_paper_data_from_url(sys.argv[1])

print(d)

print("----------------------------------")
print(harvest.get_zotero_translator_service_url(sys.argv[1]))
