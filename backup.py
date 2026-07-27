import os
import stat
import shutil
import tempfile
from datetime import datetime

import paramiko
import requests

HOST = os.environ["SFTP_HOST"]
PORT = int(os.environ["SFTP_PORT"])
USER = os.environ["SFTP_USERNAME"]
PASS = os.environ["SFTP_PASSWORD"]

REMOTE = os.environ["REMOTE_FOLDER"]

WEBHOOK = os.environ["DISCORD_WEBHOOK"]

TOKEN = os.environ["GH_TOKEN"]

REPO = os.environ["GITHUB_REPOSITORY"]

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}


def download(sftp, remote, local):
    os.makedirs(local, exist_ok=True)

    for f in sftp.listdir_attr(remote):

        rp = remote + "/" + f.filename
        lp = os.path.join(local, f.filename)

        if stat.S_ISDIR(f.st_mode):
            download(sftp, rp, lp)
        else:
            sftp.get(rp, lp)


tmp = tempfile.mkdtemp()

transport = paramiko.Transport((HOST, PORT))
transport.connect(username=USER, password=PASS)

sftp = paramiko.SFTPClient.from_transport(transport)

download(sftp, REMOTE, tmp + "/Save")

sftp.close()
transport.close()

today = datetime.utcnow().strftime("%Y-%m-%d")

zipname = f"Palworld_Backup_{today}"

zipfile = shutil.make_archive(
    zipname,
    "zip",
    tmp,
    "Save"
)

tag = today

release = requests.post(
    f"https://api.github.com/repos/{REPO}/releases",
    headers=headers,
    json={
        "tag_name": tag,
        "name": tag,
        "generate_release_notes": False
    }
)

if release.status_code == 422:

    release = requests.get(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
        headers=headers
    )

release = release.json()

upload_url = release["upload_url"].split("{")[0]

with open(zipfile, "rb") as f:

    requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/zip"
        },
        params={
            "name": os.path.basename(zipfile)
        },
        data=f
    )

release_url = release["html_url"]

requests.post(
    WEBHOOK,
    json={
        "content":
        f"✅ **Daily Palworld Backup Complete**\n\n"
        f"📅 {today}\n"
        f"📦 {os.path.basename(zipfile)}\n"
        f"🔗 {release_url}"
    }
)

releases = requests.get(
    f"https://api.github.com/repos/{REPO}/releases",
    headers=headers
).json()

if len(releases) > 30:

    for r in releases[30:]:

        requests.delete(
            f"https://api.github.com/repos/{REPO}/releases/{r['id']}",
            headers=headers
        )

        requests.delete(
            f"https://api.github.com/repos/{REPO}/git/refs/tags/{r['tag_name']}",
            headers=headers
        )

shutil.rmtree(tmp)
os.remove(zipfile)
