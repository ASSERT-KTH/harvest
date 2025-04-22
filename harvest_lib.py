import hashlib

def normalize_title(papertitle):
    # the single quote in a title is a caveat ’/'
    # the comma in a title is a caveat
    return papertitle.lower().strip().rstrip(".").replace(","," ").replace("   "," ").replace("  "," ").replace("’","'")
def path_on_disk_internal_v2(papertitle, prefix):
    assert prefix.endswith("/")
    """ returns the local file name corresponding to a paper LOWER CASE BETTER THAN V1"""
    # remove trailing space and trailing dots from paper.desc
    papertitle = normalize_title(papertitle)
    return prefix+hashlib.sha256(papertitle.encode("utf-8")).hexdigest()+".json"
