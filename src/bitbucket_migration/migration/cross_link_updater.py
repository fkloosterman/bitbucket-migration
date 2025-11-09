from typing import Dict, Any

from ..core.migration_context import MigrationEnvironment, MigrationState

from ..services.cross_repo_mapping_store import CrossRepoMappingStore
from ..services.link_rewriter import LinkRewriter

class CrossLinkUpdater:
    """
    Stage 2 service for efficiently updating GitHub issues/PRs/comments with cross-repo links.

    Only processes items that were identified during Stage 1 as containing cross-repo links.
    """
    
    def __init__(self, environment: MigrationEnvironment, state: MigrationState):
        self.environment = environment
        self.state = state

        self.logger = self.environment.logger
        self.dry_run = self.environment.dry_run

        self.cross_repo_store:CrossRepoMappingStore = self.environment.services.get('cross_repo_mapping_store')
        self.link_rewriter:LinkRewriter = self.environment.services.get('link_rewriter')
        
        self.bb_workspace = self.environment.config.bitbucket.workspace
        self.bb_repo = self.environment.config.bitbucket.repo
        self.repo_mapping = self.cross_repo_store.get_mapping(self.bb_workspace, self.bb_repo)

        self.stats = {
            'issues_updated': 0,
            'prs_updated': 0,
            'comments_updated': 0,
            'cross_repo_links_rewritten': 0,
            'unmapped_issues': 0,  # Bitbucket issues with no GitHub mapping
            'unmapped_issue_comments': 0,
            'unmapped_prs': 0,     # Bitbucket PRs with no GitHub mapping
            'unmapped_pr_comments': 0,
            'simulated_updates': 0 # Dry-run mode: updates that would be performed
        }
    
    def update_cross_repo_links(self) -> Dict[str, Any]:
        """
        Update all GitHub issues/PRs/comments that contain cross-repo links.
        
        Returns:
            Statistics about the update process
        """
        self.logger.info("="*80)
        self.logger.info("STAGE 2: Updating Cross-Repository Links")
        self.logger.info("="*80)
        
        # Update issues
        self._update_descriptions('issue')

        # Update issue comments
        self._update_comments('issue')
        
        # Update PRs  
        self._update_descriptions('pr')

        # Update PR comments
        self._update_comments('pr')
        
        if self.dry_run:
            self.logger.info("="*80)
            self.logger.info(f"DRY RUN Complete: {self.stats['issues_updated']} issues, "
                            f"{self.stats['prs_updated']} PRs, {self.stats['comments_updated']} comments would be updated")
            self.logger.info(f"Simulated updates: {self.stats['simulated_updates']}")
            self.logger.info(f"Cross-repo links that would be rewritten: {self.stats['cross_repo_links_rewritten']}")
            self.logger.info("="*80)
        else:
            self.logger.info("="*80)
            self.logger.info(f"Complete: {self.stats['issues_updated']} issues, "
                            f"{self.stats['prs_updated']} PRs, {self.stats['comments_updated']} comments updated")
            self.logger.info(f"Cross-repo links rewritten: {self.stats['cross_repo_links_rewritten']}")
            self.logger.info("="*80)
        
        return self.stats
    
    def _update_descriptions(self, kind='issue'):
        """Update GitHub issues that contain cross-repo links."""
        
        plural = kind + 's'
        label = kind if kind=='issue' else kind.capitalize()

        bb_to_update = self.repo_mapping.get('cross_repo_links',{}).get(plural)
        
        if bb_to_update:
            self.logger.info(f"Updating {len(bb_to_update)} {label} description(s) with cross-repo links...")

            for item_id in bb_to_update:
                try:
                    gh_item_id = self.repo_mapping.get(plural, {}).get(item_id)
                    if not gh_item_id:
                        self.logger.warning(f"No GitHub {label} mapping found for Bitbucket {label} #{item_id}")
                        self.stats[f'unmapped_{plural}'] += 1
                        continue
                    self.logger.info(f"Updating GitHub {label} #{gh_item_id} (was BB #{item_id})")

                    # Use get_issue() which works for both issues and PRs
                    gh_item = self.environment.clients.gh.get_issue(gh_item_id)

                    current_body = gh_item.get('body', '')
            
                    new_body, links_found, _, _, _, _, _ = self.link_rewriter.rewrite_links(
                        current_body, item_type=kind, item_number=item_id, comment_id=0  # 0 = description
                    )

                    if links_found > 0:
                        if self.dry_run:
                            self.logger.info(f"  [DRY RUN] Would update {label} #{gh_item_id} description: {links_found} cross-repo links rewritten")
                            self.stats['simulated_updates'] += 1
                        else:
                            # Use update_issue() which works for both issues and PRs
                            self.environment.clients.gh.update_issue(gh_item_id, body=new_body)

                            self.stats['cross_repo_links_rewritten'] += links_found
                            self.logger.info(f"  Updated {label} description: {links_found} cross-repo links rewritten")

                    self.stats['issues_updated'] += 1
                except Exception as e:
                    self.logger.warning(f"Failed to update description of {label} #{item_id}: {e}")

    def _update_comments(self, kind='issue'):
        
        plural = kind + 's'
        label = kind if kind == 'issue' else kind.capitalize()
        label_plural = label + 's'

        bb_comments_to_update = self.repo_mapping.get('cross_repo_links',{}).get(f'{kind}_comments')

        if bb_comments_to_update:
            self.logger.info(f"Updating {len(bb_comments_to_update)} {label_plural} with cross-repo links in comments...")

            for item_id, comment_ids in bb_comments_to_update.items():
                gh_item_id = self.repo_mapping.get(plural, {}).get(item_id)
                if not gh_item_id:
                    self.logger.warning(f"No GitHub {label} mapping found for Bitbucket {label} #{item_id}")
                    self.stats['unmapped_issue_comments'] += len(comment_ids)
                    continue
                self.logger.info(f"Updating comments of GitHub {label} #{gh_item_id} (was BB #{item_id})")

                gh_comment_ids = [self.repo_mapping.get(f'{kind}_comments',{}).get(c) for c in comment_ids]

                n_invalid = sum([c is None for c in gh_comment_ids])
                if n_invalid > 0:
                    self.logger.warning(f"Found {n_invalid} unmappable comments")

                gh_comments = self.environment.clients.gh.get_comments(gh_item_id)
                for seq, comment in enumerate(gh_comments, 1):
                    try:
                        gh_comment_id = comment['id']
                        if gh_comment_id in gh_comment_ids:
                            self.logger.info(f"Updating comment {gh_comment_id} of Github {label} #{gh_item_id}...")
                            
                            current_body = comment.get('body', '')

                            new_body, links_found, _, _, _, _, _ = self.link_rewriter.rewrite_links(
                                current_body, item_type=kind, item_number=item_id, comment_seq=seq, comment_id=gh_comment_id
                            )

                            if links_found > 0:
                                if self.dry_run:
                                    self.logger.info(f"  [DRY RUN] Would update GitHub {label} #{gh_item_id} comment {gh_comment_id}: {links_found} cross-repo links rewritten")
                                    self.stats['simulated_updates'] += 1
                                else:
                                    self.environment.clients.gh.update_comment(gh_comment_id, new_body)
                                    self.stats['comments_updated'] += 1
                                    self.stats['cross_repo_links_rewritten'] += links_found
                                    self.logger.info(f"  Updated GitHub {label} #{gh_item_id} comment {gh_comment_id}: {links_found} cross-repo links rewritten")
                    except Exception as e:
                        self.logger.warning(f"Failed to update GitHub issues #{gh_item_id} comment {gh_comment_id} : {e}")

