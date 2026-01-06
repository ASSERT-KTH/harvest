#!/usr/bin/python3
# compares zotero translator service url and harvest data extraction
import harvest
import sys

d = harvest.collect_paper_data_from_url(sys.argv[1])

print(d)

print("----------------------------------")
print(harvest.get_zotero_translator_service_url(sys.argv[1]))
