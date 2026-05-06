import unittest
from pathlib import Path


class DockerAssetTestCase(unittest.TestCase):
    def test_docker_entrypoint_uses_lf_line_endings(self):
        repo_root = Path(__file__).resolve().parents[2]
        entrypoint = repo_root / "docker-entrypoint.sh"

        content = entrypoint.read_bytes()

        self.assertNotIn(
            b"\r\n",
            content,
            "docker-entrypoint.sh must use LF line endings so /bin/bash can execute it in Linux containers",
        )

    def test_git_attributes_force_lf_for_shell_scripts(self):
        repo_root = Path(__file__).resolve().parents[2]
        git_attributes = repo_root / ".gitattributes"

        self.assertTrue(git_attributes.exists(), ".gitattributes should exist to pin shell script line endings")

        rules = git_attributes.read_text(encoding="utf-8")

        self.assertIn(
            "*.sh text eol=lf",
            rules,
            ".gitattributes must force LF for shell scripts to keep Docker entrypoints runnable on Linux",
        )


if __name__ == "__main__":
    unittest.main()
