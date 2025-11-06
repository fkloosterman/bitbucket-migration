"""
Data classes for storing service state during migration.

This module contains dataclasses that hold data for various services
during the migration process, allowing state to be maintained across
different phases of migration.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class LinkWriterData:
    """
    Data container for link rewriting operations.

    Tracks details of all link processing operations, including successful
    rewrites, failed attempts, and unmapped links.
    """
    details: List[Dict[str, Any]] = field(default_factory=list)
    unhandled_bb_links: List = field(default_factory=list)
    total_processed: int = 0
    successful: int = 0
    failed: int = 0


@dataclass
class UserMapperData:
    """
    Data container for user mapping operations.

    Stores mappings from Bitbucket account IDs to usernames and display names,
    built during the migration process for resolving @mentions.
    """
    account_id_to_username: Dict[str, str] = field(default_factory=dict)
    account_id_to_display_name: Dict[str, str] = field(default_factory=dict)


@dataclass
class AttachmentData:
    """
    Data container for attachment handling operations.

    Tracks downloaded attachments and their metadata during migration.
    """
    attachments: List[Dict] = field(default_factory=list)
    attachment_dir: str = ''
