import os
import stat
import shutil
import tempfile
from datetime import datetime

import paramiko
import requests

# ==========================
# Environment Variables
# ==========================
HOST = os.environ["SFTP_HOST"]
PORT = int(os.environ.get("SFTP_PORT", 22))
USERNAME = os.environ["SFTP_USERNAME"]
PASSWORD = os.environ["SFTP_PASSWORD"]

REMOTE_FOLDER = os.environ["REMOTE_FOLDER"]
WEBHOOK = os.environ["DISCORD_WEBHOOK"]


def download_directory(sftp, remote_dir, local_dir):
    os.makedirs(local_dir, exist_ok=True)

    for item in sftp.listdir_attr(remote_dir):
        remote_path = remote_dir + "/" + item.filename
        local_path = os.path.join(local_dir, item.filename)

        if stat.S_ISDIR(item.st_mode):
            download_directory(sftp, remote_path, local_path)
        else:
            print(f"Downloading {remote_path}")
            sftp.get(remote_path, local_path)


def main():
    temp_dir = tempfile.mkdtemp()

    try:
        transport = paramiko.Transport((HOST, PORT))
        transport.connect(username=USERNAME, password=PASSWORD)

        sftp = paramiko.SFTPClient.from_transport(transport)

        local_save = os.path.join(temp_dir, "SaveGames")

        print("Downloading save folder...")
        download_directory(sftp, REMOTE_FOLDER, local_save)

        sftp.close()
        transport.close()

        date = datetime.now().strftime("%Y-%m-%d")

        archive = shutil.make_archive(
            f"Palworld_Backup_{date}",
            "zip",
            root_dir=temp_dir,
            base_dir="SaveGames",
        )

        print("Uploading to Discord...")

        with open(archive, "rb") as f:
            r = requests.post(
                WEBHOOK,
                data={
                    "content": f"📦 Palworld backup ({date})"
                },
                files={
                    "file": f
                },
                timeout=300,
            )

        r.raise_for_status()

        print("Backup completed successfully.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

        if os.path.exists(f"Palworld_Backup_{datetime.now().strftime('%Y-%m-%d')}.zip"):
            os.remove(f"Palworld_Backup_{datetime.now().strftime('%Y-%m-%d')}.zip")


if __name__ == "__main__":
    main()
