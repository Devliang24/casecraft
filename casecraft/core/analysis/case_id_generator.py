"""Case ID generator for test cases."""

from typing import Optional

from casecraft.core.analysis.module_analyzer import ModuleAnalyzer


class CaseIdGenerator:
    """Generates unique case IDs for test cases."""
    
    def __init__(self, module_analyzer: Optional[ModuleAnalyzer] = None):
        """Initialize the case ID generator.
        
        Args:
            module_analyzer: Module analyzer instance
        """
        self.module_analyzer = module_analyzer or ModuleAnalyzer()
    
    def generate(self, module: str, method: str, index: int) -> str:
        """Generate a case ID.
        
        Args:
            module: Module name
            method: HTTP method
            index: Test case index (1-based)
            
        Returns:
            Case ID string (e.g., 'USR-GET-001')
        """
        # Get module prefix
        prefix = self.module_analyzer.get_module_prefix(module)
        
        # Get method code (first 3 letters)
        method_code = self._get_method_code(method)
        
        # Format sequence number
        sequence = f"{index:03d}"
        
        return f"{prefix}-{method_code}-{sequence}"
    
    def _get_method_code(self, method: str) -> str:
        """Get standardized method code.
        
        Args:
            method: HTTP method
            
        Returns:
            3-letter method code
        """
        method_upper = method.upper()
        
        # Standard method codes
        method_codes = {
            'GET': 'GET',
            'POST': 'POS',
            'PUT': 'PUT',
            'DELETE': 'DEL',
            'PATCH': 'PAT',
            'HEAD': 'HEA',
            'OPTIONS': 'OPT'
        }
        
        return method_codes.get(method_upper, method_upper[:3])