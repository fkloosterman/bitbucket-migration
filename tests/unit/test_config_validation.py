"""
Tests for configuration validation in unified v2.0 format.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bitbucket_migration.config.migration_config import (
    BitbucketConfig,
    ConfigLoader,
    ExternalRepositoryConfig,
    GitHubConfig,
    MigrationConfig,
    OptionsConfig,
    RepositoryConfig,
)
from bitbucket_migration.exceptions import ConfigurationError, ValidationError


class TestConfigValidation:
    """Test configuration validation for v2.0 format."""

    def test_valid_single_repo_config(self):
        """Test loading valid single repository configuration."""
        config_data = {
            "format_version": "2.0",
            "base_dir": "./test_migration",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "options": {
                "skip_issues": False,
                "skip_prs": False,
                "skip_pr_as_issue": False,
                "use_gh_cli": False
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        config = ConfigLoader.load_from_dict(config_data)

        assert config.format_version == "2.0"
        assert config.base_dir == "./test_migration"
        assert len(config.repositories) == 1
        assert config.repositories[0].bitbucket_repo == "repo1"
        assert config.repositories[0].github_repo == "repo1"
        assert config.bitbucket.workspace == "testworkspace"
        assert config.bitbucket.email == "test@example.com"
        assert config.bitbucket.token == "${BITBUCKET_TOKEN}"
        assert config.github.owner == "testorg"
        assert config.github.token == "${GITHUB_TOKEN}"
        assert config.user_mapping == {"Test User": "testuser"}

    def test_valid_multi_repo_config(self):
        """Test loading valid multi-repository configuration."""
        config_data = {
            "format_version": "2.0",
            "base_dir": "./test_migration",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                },
                {
                    "bitbucket_repo": "repo2",
                    "github_repo": "repo2"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "options": {
                "skip_issues": False,
                "skip_prs": False,
                "skip_pr_as_issue": False,
                "use_gh_cli": False
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        config = ConfigLoader.load_from_dict(config_data)

        assert config.format_version == "2.0"
        assert len(config.repositories) == 2
        assert config.repositories[0].bitbucket_repo == "repo1"
        assert config.repositories[1].bitbucket_repo == "repo2"

    def test_valid_config_with_external_repos(self):
        """Test loading valid configuration with external repositories."""
        config_data = {
            "format_version": "2.0",
            "base_dir": "./test_migration",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "external_repositories": [
                {
                    "bitbucket_repo": "external_repo",
                    "github_repo": "external_repo",
                    "github_owner": "external_org"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "options": {
                "skip_issues": False,
                "skip_prs": False,
                "skip_pr_as_issue": False,
                "use_gh_cli": False
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        config = ConfigLoader.load_from_dict(config_data)

        assert config.format_version == "2.0"
        assert len(config.repositories) == 1
        assert len(config.external_repositories) == 1
        assert config.external_repositories[0].bitbucket_repo == "external_repo"
        assert config.external_repositories[0].github_repo == "external_repo"
        assert config.external_repositories[0].github_owner == "external_org"

    def test_invalid_format_version(self):
        """Test rejection of invalid format version."""
        config_data = {
            "format_version": "1.0",
            "repositories": [],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ConfigurationError, match="Unsupported config format"):
            ConfigLoader.load_from_dict(config_data)

    def test_missing_format_version(self):
        """Test rejection of missing format version."""
        config_data = {
            "repositories": [],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ConfigurationError, match="Unsupported config format"):
            ConfigLoader.load_from_dict(config_data)

    def test_missing_repositories(self):
        """Test rejection of missing repositories array."""
        config_data = {
            "format_version": "2.0",
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ConfigurationError, match="Missing required section 'repositories'"):
            ConfigLoader.load_from_dict(config_data)

    def test_empty_repositories(self):
        """Test rejection of empty repositories array."""
        config_data = {
            "format_version": "2.0",
            "repositories": [],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="'repositories' must be a non-empty list"):
            ConfigLoader.load_from_dict(config_data)

    def test_repo_fields_in_bitbucket_section(self):
        """Test rejection of repo field in bitbucket section."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "repo": "repo1",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="bitbucket section should not have 'repo' field"):
            ConfigLoader.load_from_dict(config_data)

    def test_repo_fields_in_github_section(self):
        """Test rejection of repo field in github section."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "repo": "repo1",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="github section should not have 'repo' field"):
            ConfigLoader.load_from_dict(config_data)

    def test_missing_bitbucket_repo_field(self):
        """Test rejection of repository entry missing bitbucket_repo field."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="missing 'bitbucket_repo' field"):
            ConfigLoader.load_from_dict(config_data)

    def test_missing_github_repo_field(self):
        """Test rejection of repository entry missing github_repo field."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="missing 'github_repo' field"):
            ConfigLoader.load_from_dict(config_data)

    def test_empty_user_mapping(self):
        """Test rejection of empty user mapping."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {}
        }

        with pytest.raises(ValidationError, match="User mapping cannot be empty"):
            ConfigLoader.load_from_dict(config_data)

    def test_invalid_repository_entry_type(self):
        """Test rejection of non-dictionary repository entry."""
        config_data = {
            "format_version": "2.0",
            "repositories": ["repo1"],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="Repository entry 0 must be a dictionary"):
            ConfigLoader.load_from_dict(config_data)

    def test_invalid_external_repository_entry_type(self):
        """Test rejection of non-dictionary external repository entry."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "external_repositories": ["external_repo"],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="External repository entry 0 must be a dictionary"):
            ConfigLoader.load_from_dict(config_data)

    def test_missing_external_repo_bitbucket_repo_field(self):
        """Test rejection of external repository entry missing bitbucket_repo field."""
        config_data = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "external_repositories": [
                {
                    "github_repo": "external_repo"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ValidationError, match="missing 'bitbucket_repo' field"):
            ConfigLoader.load_from_dict(config_data)

    @patch('pathlib.Path.exists')
    @patch('builtins.open')
    def test_load_from_file_not_found(self, mock_open, mock_exists):
        """Test file not found error."""
        mock_exists.return_value = False

        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            ConfigLoader.load_from_file("nonexistent.json")

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.is_file')
    @patch('builtins.open')
    def test_load_from_file_invalid_json(self, mock_open, mock_is_file, mock_exists):
        """Test invalid JSON error."""
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = "invalid json"

        with pytest.raises(ConfigurationError, match="Invalid JSON in configuration file"):
            ConfigLoader.load_from_file("config.json")

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.is_file')
    @patch('builtins.open')
    @patch('json.load')
    def test_load_from_file_with_repo_fields(self, mock_json_load, mock_open, mock_is_file, mock_exists):
        """Test rejection of config file with repo fields in bitbucket/github sections."""
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_json_load.return_value = {
            "format_version": "2.0",
            "repositories": [
                {
                    "bitbucket_repo": "repo1",
                    "github_repo": "repo1"
                }
            ],
            "bitbucket": {
                "workspace": "testworkspace",
                "repo": "repo1",
                "email": "test@example.com",
                "token": "${BITBUCKET_TOKEN}"
            },
            "github": {
                "owner": "testorg",
                "token": "${GITHUB_TOKEN}"
            },
            "user_mapping": {
                "Test User": "testuser"
            }
        }

        with pytest.raises(ConfigurationError, match="'bitbucket.repo' field not allowed"):
            ConfigLoader.load_from_file("config.json")

    def test_config_serialization(self, tmp_path):
        """Test configuration serialization to JSON."""
        # Create a config object
        config = MigrationConfig(
            format_version="2.0",
            bitbucket=BitbucketConfig(
                workspace="testworkspace",
                repo="__unified_config__",
                email="test@example.com",
                token="${BITBUCKET_TOKEN}"
            ),
            github=GitHubConfig(
                owner="testorg",
                repo="__unified_config__",
                token="${GITHUB_TOKEN}"
            ),
            repositories=[
                RepositoryConfig(bitbucket_repo="repo1", github_repo="repo1"),
                RepositoryConfig(bitbucket_repo="repo2", github_repo="repo2")
            ],
            user_mapping={"Test User": "testuser"},
            base_dir="./test_migration",
            external_repositories=[
                ExternalRepositoryConfig(
                    bitbucket_repo="ext_repo",
                    github_repo="ext_repo",
                    github_owner="ext_org"
                )
            ],
            options=OptionsConfig(skip_issues=True, skip_prs=False)
        )

        # Test serialization by writing to a temporary file
        temp_path = tmp_path / "config.json"

        ConfigLoader.save_to_file(config, str(temp_path))

        # Read back the file and verify structure
        with open(temp_path, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)

        # Verify structure
        assert saved_config["format_version"] == "2.0"
        assert saved_config["base_dir"] == "./test_migration"
        assert len(saved_config["repositories"]) == 2
        assert len(saved_config["external_repositories"]) == 1
        assert saved_config["options"]["skip_issues"] is True
        assert saved_config["options"]["skip_prs"] is False
        # Verify repo fields are not in bitbucket/github sections
        assert "repo" not in saved_config["bitbucket"]
        assert "repo" not in saved_config["github"]