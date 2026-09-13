import json
import os
import sqlite3
import sys
import time
from pathlib import Path

json.load(sys.stdin)
connection = sqlite3.connect(os.environ["DB_PATH"])
connection.execute("BEGIN IMMEDIATE")
connection.execute("DELETE FROM expenses")
Path(os.environ["TEST_MARKER"]).touch()
time.sleep(60)
connection.commit()
