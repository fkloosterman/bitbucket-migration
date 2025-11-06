"""
Tests for audit module __init__.py.

Tests the module initialization and exports including:
- Module imports
- Class exports
- __all__ definition
"""

import pytest
from unittest.mock import patch

from bitbucket_migration.audit import AuditUtils, Auditor, AuditOrchestrator


class TestAuditModuleImports:
    """Test module import functionality."""
    
    def test_audit_utils_import(self):
        """Test that AuditUtils can be imported."""
        from bitbucket_migration.audit import AuditUtils
        assert AuditUtils is not None
        assert hasattr(AuditUtils, 'analyze_gaps')
        assert hasattr(AuditUtils, 'analyze_pr_migratability')
        assert hasattr(AuditUtils, 'calculate_migration_estimates')
        assert hasattr(AuditUtils, 'analyze_repository_structure')
        assert hasattr(AuditUtils, 'generate_migration_strategy')
    
    def test_auditor_import(self):
        """Test that Auditor can be imported."""
        from bitbucket_migration.audit import Auditor
        assert Auditor is not None
        assert hasattr(Auditor, 'run_audit')
        assert hasattr(Auditor, 'save_reports')
    
    def test_audit_orchestrator_import(self):
        """Test that AuditOrchestrator can be imported."""
        from bitbucket_migration.audit import AuditOrchestrator
        assert AuditOrchestrator is not None
        assert hasattr(AuditOrchestrator, 'discover_repositories')
        assert hasattr(AuditOrchestrator, 'audit_repositories')
        assert hasattr(AuditOrchestrator, 'generate_config')


class TestAuditModuleExports:
    """Test module export functionality."""
    
    def test_all_exports_defined(self):
        """Test that __all__ is properly defined."""
        from bitbucket_migration import audit
        
        assert hasattr(audit, '__all__')
        assert 'AuditUtils' in audit.__all__
        assert 'Auditor' in audit.__all__
        assert 'AuditOrchestrator' in audit.__all__
        assert len(audit.__all__) == 3
    
    def test_all_exports_work(self):
        """Test that all exported classes can be accessed."""
        from bitbucket_migration import audit
        
        # Should be able to access all exported classes
        assert audit.AuditUtils is not None
        assert audit.Auditor is not None
        assert audit.AuditOrchestrator is not None
    
    def test_module_level_access(self):
        """Test that classes are accessible at module level."""
        # This tests the module import functionality
        import bitbucket_migration.audit as audit_module
        
        # Verify all expected exports are available
        assert hasattr(audit_module, 'AuditUtils')
        assert hasattr(audit_module, 'Auditor')
        assert hasattr(audit_module, 'AuditOrchestrator')


class TestClassInstantiation:
    """Test that exported classes can be instantiated."""
    
    def test_audit_utils_instantiation(self):
        """Test that AuditUtils can be instantiated."""
        from bitbucket_migration.audit import AuditUtils
        
        utils = AuditUtils()
        assert isinstance(utils, AuditUtils)
    
    @pytest.mark.parametrize("cls,args,kwargs", [
        (Auditor, 
         ("workspace", "repo", "email", "token"), 
         {}),
        (AuditOrchestrator,
         ("workspace", "email", "token"),
         {}),
    ])
    def test_auditor_orchestrator_instantiation(self, cls, args, kwargs):
        """Test that Auditor and AuditOrchestrator can be instantiated with valid params."""
        if cls == Auditor:
            test_args = ("test-workspace", "test-repo", "test@example.com", "test-token")
        else:  # AuditOrchestrator
            test_args = ("test-workspace", "test@example.com", "test-token")
        
        instance = cls(*test_args, **kwargs)
        assert isinstance(instance, cls)
    
    def test_auditor_instantiation_fails_with_invalid_params(self):
        """Test that Auditor fails with invalid parameters."""
        from bitbucket_migration.audit import Auditor
        from bitbucket_migration.exceptions import ValidationError
        
        # Test with empty workspace
        with pytest.raises(ValidationError):
            Auditor("", "repo", "email", "token")
        
        # Test with empty repo
        with pytest.raises(ValidationError):
            Auditor("workspace", "", "email", "token")
        
        # Test with empty email
        with pytest.raises(ValidationError):
            Auditor("workspace", "repo", "", "token")
        
        # Test with empty token
        with pytest.raises(ValidationError):
            Auditor("workspace", "repo", "email", "")
    
    def test_audit_orchestrator_instantiation_fails_with_invalid_params(self):
        """Test that AuditOrchestrator fails with invalid parameters."""
        from bitbucket_migration.audit import AuditOrchestrator
        from bitbucket_migration.exceptions import ValidationError
        
        # Test with empty workspace
        with pytest.raises(ValidationError):
            AuditOrchestrator("", "email", "token")
        
        # Test with empty email
        with pytest.raises(ValidationError):
            AuditOrchestrator("workspace", "", "token")
        
        # Test with empty token
        with pytest.raises(ValidationError):
            AuditOrchestrator("workspace", "email", "")


class TestModuleDocstring:
    """Test module documentation."""
    
    def test_module_docstring_exists(self):
        """Test that module has a docstring."""
        from bitbucket_migration import audit
        
        assert audit.__doc__ is not None
        assert "Bitbucket Migration Audit Module" in audit.__doc__
        assert "migration" in audit.__doc__.lower()
        assert "audit" in audit.__doc__.lower()
    
    def test_module_docstring_content(self):
        """Test that module docstring contains expected content."""
        from bitbucket_migration import audit
        
        docstring = audit.__doc__
        
        # Should mention audit functionality
        assert "audit" in docstring.lower()
        
        # Should mention migration planning
        assert "migration" in docstring.lower()
        
        # Should mention repository structure analysis
        assert "repository" in docstring.lower()
        
        # Should mention user mappings
        assert "user" in docstring.lower()