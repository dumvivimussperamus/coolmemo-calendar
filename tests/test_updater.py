import unittest
from unittest import mock

from coolmemo_app import updater


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertTrue(updater.is_newer("v1.1.1", "1.1.0"))
        self.assertTrue(updater.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(updater.is_newer("v1.1.0", "1.1.0"))
        self.assertFalse(updater.is_newer("v1.0.9", "1.1.0"))


class SummaryTests(unittest.TestCase):
    def release(self, url, digest):
        return {
            "tag_name": "v9.9.9",
            "body": "notes",
            "assets": [{"name": updater.INSTALLER_ASSET, "browser_download_url": url, "digest": digest}],
        }

    def test_requires_trusted_url_and_digest(self):
        good_url = updater.DOWNLOAD_PREFIX + "v9.9.9/" + updater.INSTALLER_ASSET
        with mock.patch.object(updater, "is_installed_build", return_value=True):
            ok = updater._summarize(self.release(good_url, "sha256:" + "a" * 64))
            self.assertTrue(ok["available"] and ok["canAutoInstall"])
            evil = updater._summarize(self.release("https://evil.example/x.exe", "sha256:" + "a" * 64))
            self.assertFalse(evil["canAutoInstall"])
            nodigest = updater._summarize(self.release(good_url, ""))
            self.assertFalse(nodigest["canAutoInstall"])

    def test_portable_never_auto_installs(self):
        good_url = updater.DOWNLOAD_PREFIX + "v9.9.9/" + updater.INSTALLER_ASSET
        with mock.patch.object(updater, "is_installed_build", return_value=False):
            summary = updater._summarize(self.release(good_url, "sha256:" + "a" * 64))
            self.assertFalse(summary["canAutoInstall"])


if __name__ == "__main__":
    unittest.main()
