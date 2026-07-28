import os
import stat
import time
import shutil
import tempfile
import posixpath
from datetime import datetime

import paramiko
import requests

# ------------------------------------------------------------------
# Environment Variables
# ------------------------------------------------------------------
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

# Track skipped files during SFTP traversal
skipped_items = []


def download_with_retry(sftp, remote_path, local_path, retries=3, delay=2):
    """Attempt to download a file with retry logic for locked files."""
    for attempt in range(1, retries + 1):
        try:
            sftp.get(remote_path, local_path)
            return True
        except Exception as e:
            if attempt < retries:
                print(f"🔄 Retry {attempt}/{retries} for file '{remote_path}' after error: {e}")
                time.sleep(delay)
            else:
                print(f"❌ Failed to download '{remote_path}' after {retries} attempts: {e}")
                skipped_items.append(f"File: {remote_path} ({e})")
                return False


def listdir_with_retry(sftp, remote_path, retries=3, delay=2):
    """Attempt to list directory contents with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            return sftp.listdir_attr(remote_path)
        except Exception as e:
            if attempt < retries:
                print(f"🔄 Retry {attempt}/{retries} listing directory '{remote_path}' after error: {e}")
                time.sleep(delay)
            else:
                print(f"❌ Could not list directory '{remote_path}' after {retries} attempts: {e}")
                skipped_items.append(f"Directory: {remote_path} ({e})")
                return None


def download(sftp, remote, local):
    """Recursively download files from SFTP with retries and error handling."""
    os.makedirs(local, exist_ok=True)

    items = listdir_with_retry(sftp, remote)
    if items is None:
        return

    for f in items:
        # Use posixpath for SFTP paths
        rp = posixpath.join(remote, f.filename)
        lp = os.path.join(local, f.filename)

        if stat.S_ISDIR(f.st_mode):
            download(sftp, rp, lp)
        elif stat.S_ISREG(f.st_mode):
            download_with_retry(sftp, rp, lp)


# ------------------------------------------------------------------
# Main Backup Execution
# ------------------------------------------------------------------
tmp = tempfile.mkdtemp()

try:
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)

    download(sftp, REMOTE, os.path.join(tmp, "Save"))

    sftp.close()
    transport.close()
except Exception as e:
    # Send Discord notification if connection or traversal fails completely
    requests.post(
        WEBHOOK,
        json={"content": f"🚨 **Palworld Backup Failed!**\n`SFTP Error: {e}`"}
    )
    raise

# Create zip archive
today = datetime.utcnow().strftime("%Y-%m-%d")
zipname = f"Palworld_Backup_{today}"

zipfile = shutil.make_archive(
    zipname,
    "zip",
    tmp,
    "Save"
)

# ------------------------------------------------------------------
# GitHub Release Management
# ------------------------------------------------------------------
tag = today

# Try creating a new release
release = requests.post(
    f"https://api.github.com/repos/{REPO}/releases",
    headers=headers,
    json={
        "tag_name": tag,
        "name": tag,
        "generate_release_notes": False
    }
)

# If release for today already exists, fetch existing release details
if release.status_code == 422:
    release = requests.get(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}",
        headers=headers
    )

release_data = release.json()
upload_url = release_data["upload_url"].split("{")[0]

# Upload the ZIP artifact
with open(zipfile, "rb") as f:
    requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/zip"
        },
        params={"name": os.path.basename(zipfile)},
        data=f
    )

release_url = release_data.get("html_url", f"https://github.com/{REPO}/releases")

# ------------------------------------------------------------------
# Discord Notification
# ------------------------------------------------------------------
status_msg = f"✅ **Daily Palworld Backup Complete**\n\n📅 {today}\n📦 {os.path.basename(zipfile)}\n🔗 {release_url}"

if skipped_items:
    status_msg += f"\n\n⚠️ **Note:** {len(skipped_items)} item(s) skipped after retries (likely locked by server)."

requests.post(WEBHOOK, json={"content": status_msg})

# ------------------------------------------------------------------
# Retention Cleanup (Keep Last 30 Releases)
# ------------------------------------------------------------------
releases_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/releases",
    headers=headers
)

if releases_resp.status_code == 200:
    releases = releases_resp.json()
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

# Clean up local temporary files
shutil.rmtree(tmp)
if os.path.exists(zipfile):
    os.remove(zipfile)
