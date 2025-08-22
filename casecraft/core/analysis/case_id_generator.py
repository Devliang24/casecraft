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
    
    def generate(self, module: str, method: str, index: int, test_type: str = None) -> str:
        """Generate a case ID.
        
        Args:
            module: Module name
            method: HTTP method
            index: Test case index (1-based)
            test_type: Test type (positive/negative/boundary)
            
        Returns:
            Case ID string (e.g., 'USR-POS-001' for positive, 'USR-NEG-001' for negative)
        """
        # Get module prefix
        prefix = self.module_analyzer.get_module_prefix(module)
        
        # Get type code based on test_type if provided, otherwise use method
        if test_type:
            type_code = self._get_type_code(test_type)
        else:
            # Fallback to method code for backward compatibility
            type_code = self._get_method_code(method)
        
        # Format sequence number
        sequence = f"{index:03d}"
        
        return f"{prefix}-{type_code}-{sequence}"
    
    def _get_type_code(self, test_type: str) -> str:
        """Get standardized test type code.
        
        Args:
            test_type: Test type (positive/negative/boundary)
            
        Returns:
            3-letter type code
        """
        type_codes = {
            'positive': 'POS',
            'negative': 'NEG',
            'boundary': 'BND'
        }
        
        return type_codes.get(test_type.lower(), 'UNK')
    
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