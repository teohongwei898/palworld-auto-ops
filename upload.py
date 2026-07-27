import os
import sys
import paramiko
import requests

HOST = os.environ["SFTP_HOST"]
PORT = int(os.environ.get("SFTP_PORT", 22))
USERNAME = os.environ["SFTP_USERNAME"]
PASSWORD = os.environ["SFTP_PASSWORD"]

REMOTE_FILE = os.environ["REMOTE_FILE"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]

filename = os.path.basename(REMOTE_FILE)

transport = paramiko.Transport((HOST, PORT))
transport.connect(username=USERNAME, password=PASSWORD)

sftp = paramiko.SFTPClient.from_transport(transport)

try:
    sftp.get(REMOTE_FILE, filename)
finally:
    sftp.close()
    transport.close()

with open(filename, "rb") as f:
    r = requests.post(
        WEBHOOK,
        data={"content": f"Daily upload: `{filename}`"},
        files={"file": f},
        timeout=60,
    )

if r.status_code >= 300:
    print(r.text)
    sys.exit(1)

print("Success")
