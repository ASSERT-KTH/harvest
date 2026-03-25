#!/usr/bin/python

from harvest import *


def notify_for_keyword_chains():
    """
    python -c "import harvest; harvest.notify_for_keyword_chains()"
    """
    return notify_for_all_keyword("Chains")

if __name__ == "__main__":
    notify_for_keyword_chains()