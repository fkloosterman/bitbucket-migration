import re
from typing import Dict, Tuple, Optional, List, Any

from .user_mapper import UserMapper

class LinkRewriter:
    def __init__(self, issue_mapping: Dict[int, int], pr_mapping: Dict[int, int],
                  repo_mapping: Dict[str, str], bb_workspace: str, bb_repo: str,
                  gh_owner: str, gh_repo: str, user_mapper: UserMapper):
         self.issue_mapping = issue_mapping
         self.pr_mapping = pr_mapping
         self.repo_mapping = repo_mapping
         self.bb_workspace = bb_workspace
         self.bb_repo = bb_repo
         self.gh_owner = gh_owner
         self.gh_repo = gh_repo
         self.user_mapper = user_mapper
         self.unhandled_bb_links = []
         # New attributes for tracking link rewriting metrics
         self.link_details: List[Dict[str, Any]] = []
         self.total_processed: int = 0
         self.successful: int = 0
         self.failed: int = 0
    
    def rewrite_links(self, text: str, item_type: str = 'issue',
                      item_number: Optional[int] = None) -> Tuple[str, int, List[Dict], int, int, List[str]]:
        """Rewrite Bitbucket links in text to GitHub equivalents"""
        if not text:
            return text, 0, [], 0, 0, []
        
        original_text = text
        links_found = 0
        
        # Rewrite issue URLs
        text, issue_links = self._rewrite_issue_links(text)
        links_found += issue_links
        
        # Rewrite PR URLs  
        text, pr_links = self._rewrite_pr_links(text)
        links_found += pr_links
        
        # Rewrite commit URLs
        text, commit_links = self._rewrite_commit_links(text)
        links_found += commit_links
        
        # Rewrite commit references like <<cset ...>>
        text, commit_ref_links = self._rewrite_commit_refs(text)
        links_found += commit_ref_links
        
        # Rewrite branch URLs
        text, branch_links = self._rewrite_branch_links(text)
        links_found += branch_links
        
        # Rewrite compare URLs
        text, compare_links = self._rewrite_compare_links(text)
        links_found += compare_links
        
        # Rewrite cross-repo links
        text, cross_links = self._rewrite_cross_repo_links(text)
        links_found += cross_links
        
        # Rewrite repo home links
        text, repo_links = self._rewrite_repo_home_links(text)
        links_found += repo_links
        
        # Rewrite mentions
        text, mention_replaced, mention_unmapped, unmapped_list = self._rewrite_mentions(text)
        # Note: mentions don't count as links_found
        
        # Rewrite short issue references
        text, short_issue_links = self._rewrite_short_issue_refs(text)
        links_found += short_issue_links
        
        # Rewrite PR references
        text, pr_ref_links = self._rewrite_pr_refs(text)
        links_found += pr_ref_links
        
        # Detect unhandled links
        self._detect_unhandled_links(text, item_type, item_number)
        
        return text, links_found, self.unhandled_bb_links, mention_replaced, mention_unmapped, unmapped_list
    
    def _rewrite_issue_links(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket issue URLs to GitHub"""
        pattern = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/issues/(\d+)'
        links_found = 0
        
        def replace_issue_url(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.issue_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                rewritten = f"[#{gh_num}]({gh_url}) *(was [BB #{bb_num}]({match.group(0)}))*"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'issue_link',
                    'reason': 'mapped'
                })
                self.successful += 1
            else:
                rewritten = match.group(0)
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'issue_link',
                    'reason': 'unmapped'
                })
                self.failed += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_issue_url, text), links_found
    
    def _rewrite_pr_links(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket PR URLs to GitHub"""
        pattern = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/pull-requests/(\d+)'
        links_found = 0
        
        def replace_pr_url(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.pr_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                # For simplicity, assume it's an issue unless specified
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                rewritten = f"[#{gh_num}]({gh_url}) *(was [BB PR #{bb_num}]({match.group(0)}))*"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'pr_link',
                    'reason': 'mapped'
                })
                self.successful += 1
            else:
                rewritten = match.group(0)
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'pr_link',
                    'reason': 'unmapped'
                })
                self.failed += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_pr_url, text), links_found
    
    def _rewrite_commit_links(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket commit URLs to GitHub"""
        pattern = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/commits/([0-9a-f]{{7,40}})'
        links_found = 0
        
        def replace_commit_url(match):
            nonlocal links_found
            commit_sha = match.group(1)
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commit/{commit_sha}"
            rewritten = f"[`{commit_sha[:7]}`]({gh_url}) *(was [Bitbucket]({match.group(0)}))*"
            self.link_details.append({
                'original': match.group(0),
                'rewritten': rewritten,
                'type': 'commit_link',
                'reason': 'mapped'
            })
            self.successful += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_commit_url, text), links_found
    
    def _rewrite_commit_refs(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket commit references like <<cset ...>> to GitHub"""
        pattern = r'<<cset\s+([0-9a-fA-F]+)>>'
        links_found = 0
        
        def replace_commit_ref(match):
            nonlocal links_found
            commit_sha = match.group(1)
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commit/{commit_sha}"
            rewritten = f"[`{commit_sha[:7]}`]({gh_url}) *(was Bitbucket commit reference)*"
            self.link_details.append({
                'original': match.group(0),
                'rewritten': rewritten,
                'type': 'commit_ref',
                'reason': 'mapped'
            })
            self.successful += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_commit_ref, text), links_found
    
    def _rewrite_branch_links(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket branch commit URLs to GitHub"""
        pattern = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/commits/branch/([^/\s\)]+)'
        links_found = 0
        
        def replace_branch_url(match):
            nonlocal links_found
            branch_name = match.group(1)
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/commits/{branch_name}"
            rewritten = f"[commits on `{branch_name}`]({gh_url}) *(was [Bitbucket]({match.group(0)}))*"
            self.link_details.append({
                'original': match.group(0),
                'rewritten': rewritten,
                'type': 'branch_link',
                'reason': 'mapped'
            })
            self.successful += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_branch_url, text), links_found
    
    def _rewrite_compare_links(self, text: str) -> Tuple[str, int]:
        """Rewrite Bitbucket compare URLs to GitHub"""
        pattern = rf'https://bitbucket\.org/{self.bb_workspace}/{self.bb_repo}/compare/([0-9a-f]{{7,40}})\.\.([0-9a-f]{{7,40}})'
        links_found = 0
        
        def replace_compare_url(match):
            nonlocal links_found
            sha1 = match.group(1)
            sha2 = match.group(2)
            links_found += 1
            gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/compare/{sha1}...{sha2}"
            rewritten = f"[compare `{sha1[:7]}`...`{sha2[:7]}`]({gh_url}) *(was [Bitbucket]({match.group(0)}))*"
            self.link_details.append({
                'original': match.group(0),
                'rewritten': rewritten,
                'type': 'compare_link',
                'reason': 'mapped'
            })
            self.successful += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_compare_url, text), links_found
    
    def _rewrite_cross_repo_links(self, text: str) -> Tuple[str, int]:
        """Rewrite cross-repository links"""
        pattern = r'https://bitbucket\.org/([^/]+)/([^/]+)/(issues|src|commits)(/[^\s\)"\'>]+)'
        links_found = 0
        
        def replace_cross_repo(match):
            nonlocal links_found
            workspace = match.group(1)
            repo = match.group(2)
            resource_type = match.group(3)
            resource_path = match.group(4)[1:]
            
            if workspace == self.bb_workspace and repo == self.bb_repo:
                gh_owner = self.gh_owner
                gh_repo = self.gh_repo
                mapped = True
            else:
                repo_key = f"{workspace}/{repo}"
                if repo_key not in self.repo_mapping:
                    rewritten = match.group(0)
                    self.link_details.append({
                        'original': match.group(0),
                        'rewritten': rewritten,
                        'type': 'cross_repo_link',
                        'reason': 'unmapped'
                    })
                    self.failed += 1
                    self.total_processed += 1
                    return rewritten
                gh_repo_full = self.repo_mapping[repo_key]
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    gh_owner = self.gh_owner
                    gh_repo = gh_repo_full
                mapped = True
            
            links_found += 1
            bb_url = match.group(0)
            
            if resource_type == 'issues':
                issue_number = resource_path.split('/')[0]
                if workspace == self.bb_workspace and repo == self.bb_repo:
                    gh_issue_num = self.issue_mapping.get(int(issue_number), int(issue_number))
                    gh_url = f"https://github.com/{gh_owner}/{gh_repo}/issues/{gh_issue_num}"
                    if int(issue_number) != gh_issue_num:
                        rewritten = f"[#{gh_issue_num}]({gh_url}) *(was BB #{issue_number})*"
                    else:
                        rewritten = f"[#{gh_issue_num}]({gh_url})"
                else:
                    gh_url = f"https://github.com/{gh_owner}/{gh_repo}/issues/{issue_number}"
                    rewritten = f"[{gh_repo} #{issue_number}]({gh_url}) *(was [Bitbucket {repo}]({bb_url}))*"
            elif resource_type == 'src':
                parts = resource_path.split('/', 1)
                if len(parts) == 2:
                    ref, file_path = parts
                    if '#lines-' in file_path:
                        file_path, line_ref = file_path.split('#lines-', 1)
                        gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{ref}/{file_path}#L{line_ref}"
                    else:
                        gh_url = f"https://github.com/{gh_owner}/{gh_repo}/blob/{ref}/{file_path}"
                    filename = file_path.split('/')[-1]
                    if workspace == self.bb_workspace and repo == self.bb_repo:
                        rewritten = f"[{filename}]({gh_url})"
                    else:
                        rewritten = f"[{gh_repo}/{filename}]({gh_url}) *(was [Bitbucket]({bb_url}))*"
                else:
                    rewritten = match.group(0)
            elif resource_type == 'commits':
                commit_hash = resource_path.split('/')[0]
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}/commit/{commit_hash}"
                if workspace == self.bb_workspace and repo == self.bb_repo:
                    rewritten = f"[`{commit_hash[:7]}`]({gh_url})"
                else:
                    rewritten = f"[{gh_repo}@{commit_hash[:7]}]({gh_url}) *(was [Bitbucket]({bb_url}))*"
            else:
                rewritten = match.group(0)
            
            self.link_details.append({
                'original': match.group(0),
                'rewritten': rewritten,
                'type': 'cross_repo_link',
                'reason': 'mapped' if mapped else 'unmapped'
            })
            if mapped:
                self.successful += 1
            else:
                self.failed += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_cross_repo, text), links_found
    
    def _rewrite_repo_home_links(self, text: str) -> Tuple[str, int]:
        """Rewrite repository home page links"""
        pattern = r'https://bitbucket\.org/([^/]+)/([^/\s\)"\'>]+)(?=/|\s|\)|"|\'|>|$)'
        links_found = 0
        
        def replace_repo_home(match):
            nonlocal links_found
            workspace = match.group(1)
            repo = match.group(2)
            
            if workspace == self.bb_workspace and repo == self.bb_repo:
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}"
                rewritten = f"[repository]({gh_url})"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'repo_home_link',
                    'reason': 'mapped'
                })
                self.successful += 1
                self.total_processed += 1
                return rewritten
            
            repo_key = f"{workspace}/{repo}"
            if repo_key in self.repo_mapping:
                links_found += 1
                gh_repo_full = self.repo_mapping[repo_key]
                if '/' in gh_repo_full:
                    gh_owner, gh_repo = gh_repo_full.split('/', 1)
                else:
                    gh_owner = self.gh_owner
                    gh_repo = gh_repo_full
                gh_url = f"https://github.com/{gh_owner}/{gh_repo}"
                rewritten = f"[{gh_repo}]({gh_url}) *(was [Bitbucket {repo}]({match.group(0)}))*"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'repo_home_link',
                    'reason': 'mapped'
                })
                self.successful += 1
                self.total_processed += 1
                return rewritten
            else:
                rewritten = match.group(0)
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'repo_home_link',
                    'reason': 'unmapped'
                })
                self.failed += 1
                self.total_processed += 1
                return rewritten
        
        return re.sub(pattern, replace_repo_home, text), links_found
    
    def _rewrite_mentions(self, text: str) -> Tuple[str, int, int, List[str]]:
        """Rewrite @mentions"""
        pattern = r'(?<![a-zA-Z0-9_.])@(\{[^}]+\}|[a-zA-Z0-9_][a-zA-Z0-9_-]*)'
        mentions_replaced = 0
        mentions_unmapped = 0
        unmapped_list = []
        
        def replace_mention(match):
            nonlocal mentions_replaced, mentions_unmapped, unmapped_list
            bb_mention = match.group(1)
            
            if bb_mention.startswith('{') and bb_mention.endswith('}'):
                bb_username = bb_mention[1:-1]
                bb_username_normalized = bb_username.replace(' ', '-')
            else:
                bb_username = bb_mention
                bb_username_normalized = bb_username
            
            gh_username = self.user_mapper.map_mention(bb_username)
            
            if gh_username:
                mentions_replaced += 1
                rewritten = f"@{gh_username}"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'mention',
                    'reason': 'mapped'
                })
                self.successful += 1
            else:
                is_account_id = ':' in bb_username or (len(bb_username) == 24 and all(c in '0123456789abcdef' for c in bb_username.lower()))
                
                if is_account_id:
                    display_name = self.user_mapper.account_id_to_display_name.get(bb_username)
                    if display_name:
                        mentions_unmapped += 1
                        unmapped_list.append(bb_username)
                        rewritten = f"**{display_name}** *(Bitbucket user, no GitHub account)*"
                    else:
                        mentions_unmapped += 1
                        unmapped_list.append(bb_username)
                        rewritten = f"@{bb_username_normalized} *(Bitbucket user, needs GitHub mapping)*"
                else:
                    mentions_unmapped += 1
                    unmapped_list.append(bb_username)
                    rewritten = f"@{bb_username_normalized} *(Bitbucket user, needs GitHub mapping)*"
                
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'mention',
                    'reason': 'unmapped'
                })
                self.failed += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_mention, text), mentions_replaced, mentions_unmapped, unmapped_list
    
    def _rewrite_short_issue_refs(self, text: str) -> Tuple[str, int]:
        """Rewrite short issue references like #123"""
        pattern = r'(?<!\bPR\s)(?<!\bpull request\s)(?<!\[)(?<!BB )#(\d+)(?!\])'
        links_found = 0

        def replace_short_issue(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.issue_mapping.get(bb_num)
            if gh_num and bb_num != gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                rewritten = f"[#{gh_num}]({gh_url}) *(was BB `#{bb_num}`)*"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'short_issue_ref',
                    'reason': 'mapped'
                })
                self.successful += 1
            elif gh_num and bb_num == gh_num:
                links_found += 1
                rewritten = f"#{gh_num}"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'short_issue_ref',
                    'reason': 'mapped'
                })
                self.successful += 1
            else:
                rewritten = match.group(0)
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'short_issue_ref',
                    'reason': 'unmapped'
                })
                self.failed += 1
            self.total_processed += 1
            return rewritten

        return re.sub(pattern, replace_short_issue, text, flags=re.IGNORECASE), links_found
    
    def _rewrite_pr_refs(self, text: str) -> Tuple[str, int]:
        """Rewrite PR references like PR #45"""
        pattern = r'(?:PR|pull request)\s*#(\d+)'
        links_found = 0
        
        def replace_pr_ref(match):
            nonlocal links_found
            bb_num = int(match.group(1))
            gh_num = self.pr_mapping.get(bb_num)
            
            if gh_num:
                links_found += 1
                gh_url = f"https://github.com/{self.gh_owner}/{self.gh_repo}/issues/{gh_num}"
                rewritten = f"[#{gh_num}]({gh_url}) *(was BB PR `#{bb_num}`)*"
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'pr_ref',
                    'reason': 'mapped'
                })
                self.successful += 1
            else:
                rewritten = match.group(0)
                self.link_details.append({
                    'original': match.group(0),
                    'rewritten': rewritten,
                    'type': 'pr_ref',
                    'reason': 'unmapped'
                })
                self.failed += 1
            self.total_processed += 1
            return rewritten
        
        return re.sub(pattern, replace_pr_ref, text, flags=re.IGNORECASE), links_found
    
    def _detect_unhandled_links(self, text: str, item_type: str, item_number: Optional[int]):
        """Detect unhandled Bitbucket links"""
        remaining_bb_pattern = r'https?://(?:www\.)?bitbucket\.org/[^\s\)"\'>]+'
        remaining_matches = re.findall(remaining_bb_pattern, text)
        for unhandled_url in remaining_matches:
            if '*(was' not in text[max(0, text.find(unhandled_url)-50):text.find(unhandled_url)+len(unhandled_url)+50]:
                self.unhandled_bb_links.append({
                    'url': unhandled_url,
                    'item_type': item_type,
                    'item_number': item_number,
                    'context': text[max(0, text.find(unhandled_url)-50):min(len(text), text.find(unhandled_url)+len(unhandled_url)+50)]
                })
                self.link_details.append({
                    'original': unhandled_url,
                    'rewritten': unhandled_url,
                    'type': 'unhandled',
                    'reason': 'unhandled'
                })
                self.failed += 1
                self.total_processed += 1