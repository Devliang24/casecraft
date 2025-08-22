"""Zero-config module detection for API endpoints."""

import re
from typing import Dict, List, Optional, Set
from collections import defaultdict

from casecraft.models.api_spec import APIEndpoint


class ZeroConfigModuleDetector:
    """Automatically detect and group API modules without any configuration."""
    
    def __init__(self, lang: Optional[str] = None):
        """Initialize the detector.
        
        Args:
            lang: Optional language code for translations (e.g., 'zh', 'en')
        """
        self.lang = lang
        self._prefix_cache: Set[str] = set()
        
    def detect(self, endpoints: List[APIEndpoint]) -> Dict[str, Dict]:
        """Detect modules from API endpoints.
        
        Args:
            endpoints: List of API endpoints
            
        Returns:
            Dictionary mapping module keys to module information
        """
        modules = {}
        
        # First priority: Use OpenAPI tags if available
        if self._has_meaningful_tags(endpoints):
            modules = self._detect_from_tags(endpoints)
        else:
            # Second priority: Analyze path patterns
            modules = self._detect_from_paths(endpoints)
        
        # Generate smart prefixes for all modules
        for module_key, module_info in modules.items():
            if 'prefix' not in module_info:
                module_info['prefix'] = self._generate_unique_prefix(module_key)
        
        # Optional: Apply translations if language is specified
        if self.lang:
            for module_info in modules.values():
                module_info['display_name'] = self._translate_if_needed(
                    module_info['name'], 
                    self.lang
                )
        
        return modules
    
    def _has_meaningful_tags(self, endpoints: List[APIEndpoint]) -> bool:
        """Check if endpoints have meaningful tags."""
        tags = set()
        for endpoint in endpoints:
            if hasattr(endpoint, 'tags') and endpoint.tags:
                tags.update(endpoint.tags)
        
        # Consider tags meaningful if we have at least 2 different tags
        # and they're not just generic tags
        if len(tags) >= 2:
            generic_tags = {'api', 'default', 'general', 'other'}
            meaningful_tags = tags - generic_tags
            return len(meaningful_tags) >= 1
        
        return False
    
    def _detect_from_tags(self, endpoints: List[APIEndpoint]) -> Dict[str, Dict]:
        """Detect modules from OpenAPI tags."""
        modules = {}
        
        for endpoint in endpoints:
            if hasattr(endpoint, 'tags') and endpoint.tags:
                for tag in endpoint.tags:
                    if tag not in modules:
                        modules[tag] = {
                            'name': tag,
                            'endpoints': [],
                            'endpoint_count': 0
                        }
                    modules[tag]['endpoints'].append(endpoint.get_endpoint_id())
                    modules[tag]['endpoint_count'] += 1
        
        return modules
    
    def _detect_from_paths(self, endpoints: List[APIEndpoint]) -> Dict[str, Dict]:
        """Detect modules by analyzing path patterns."""
        # Group endpoints by their resource patterns
        path_groups = defaultdict(list)
        
        for endpoint in endpoints:
            resource = self._extract_resource_from_path(endpoint.path)
            path_groups[resource].append(endpoint.get_endpoint_id())
        
        # Convert to module dictionary
        modules = {}
        for resource, endpoint_ids in path_groups.items():
            modules[resource] = {
                'name': resource,
                'endpoints': endpoint_ids,
                'endpoint_count': len(endpoint_ids)
            }
        
        return modules
    
    def _extract_resource_from_path(self, path: str) -> str:
        """Extract the main resource name from an API path.
        
        Examples:
            /api/v1/users -> users
            /api/v2/user-management -> user-management
            /products/{id}/reviews -> products
            /admin/system/config -> admin-system
        """
        # Remove leading/trailing slashes
        path = path.strip('/')
        
        # Split into segments
        segments = path.split('/')
        
        # Filter out common prefixes and parameters
        meaningful_segments = []
        for segment in segments:
            # Skip parameters
            if segment.startswith('{') and segment.endswith('}'):
                continue
            
            # Skip version indicators
            if re.match(r'^v\d+$', segment):
                continue
            
            # Skip common API prefixes
            if segment.lower() in ['api', 'rest', 'service', 'services']:
                continue
            
            # This looks like a meaningful segment
            meaningful_segments.append(segment)
        
        if meaningful_segments:
            # For nested resources, combine first two meaningful segments
            if len(meaningful_segments) >= 2 and meaningful_segments[0] in ['admin', 'internal', 'public']:
                return f"{meaningful_segments[0]}-{meaningful_segments[1]}"
            
            # Return the first meaningful segment
            return meaningful_segments[0]
        
        # Fallback
        return 'general'
    
    def _generate_unique_prefix(self, module_name: str) -> str:
        """Generate a unique prefix for a module.
        
        Examples:
            users -> USR
            products -> PRD
            user-management -> UMGT
            shopping-cart -> SHCA
        """
        # Clean the name
        clean_name = re.sub(r'[^a-zA-Z0-9\s\-_]', '', module_name)
        
        # Try different strategies until we get a unique prefix
        prefix = self._try_acronym(clean_name)
        if prefix not in self._prefix_cache:
            self._prefix_cache.add(prefix)
            return prefix
        
        prefix = self._try_consonants(clean_name)
        if prefix not in self._prefix_cache:
            self._prefix_cache.add(prefix)
            return prefix
        
        prefix = self._try_with_number(clean_name)
        self._prefix_cache.add(prefix)
        return prefix
    
    def _try_acronym(self, name: str) -> str:
        """Try to create prefix from acronym."""
        # Handle hyphenated or underscored names
        if '-' in name or '_' in name:
            parts = re.split(r'[-_]', name)
            acronym = ''.join(p[0].upper() for p in parts if p)
            return acronym[:4]
        
        # Handle camelCase or PascalCase
        words = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)', name)
        if len(words) > 1:
            return ''.join(w[0].upper() for w in words)[:4]
        
        # Single word: take first 3 characters
        return name[:3].upper() if len(name) >= 3 else name.upper()
    
    def _try_consonants(self, name: str) -> str:
        """Try to create prefix from consonants."""
        clean = name.upper().replace('-', '').replace('_', '')
        
        # First letter + consonants
        if clean:
            first = clean[0]
            consonants = [c for c in clean[1:] if c not in 'AEIOU']
            
            if consonants:
                return first + ''.join(consonants[:2])
            else:
                # Fall back to first 3 chars
                return clean[:3]
        
        return 'GEN'
    
    def _try_with_number(self, name: str) -> str:
        """Generate prefix with a number suffix for uniqueness."""
        base = self._try_acronym(name)[:3]
        
        # Find a number that makes it unique
        for i in range(1, 10):
            candidate = f"{base}{i}"
            if candidate not in self._prefix_cache:
                return candidate
        
        # Fallback: use first 2 chars + 2 digit number
        import random
        return f"{name[:2].upper()}{random.randint(10, 99)}"
    
    def _translate_if_needed(self, term: str, lang: str) -> str:
        """Optionally translate common terms.
        
        This is a simple translation for common API terms.
        For production, this could use a translation service.
        """
        if lang == 'zh':
            # Common technical terms translation
            translations = {
                'users': '用户',
                'user': '用户',
                'auth': '认证',
                'authentication': '认证',
                'products': '产品',
                'product': '产品',
                'orders': '订单',
                'order': '订单',
                'cart': '购物车',
                'payment': '支付',
                'admin': '管理',
                'categories': '分类',
                'category': '分类',
                'items': '项目',
                'item': '项目',
                'general': '通用',
                # Add more as needed, but keep it generic
            }
            
            # Try exact match first
            lower_term = term.lower()
            if lower_term in translations:
                return translations[lower_term]
            
            # Try matching the last word (for compound terms)
            words = re.split(r'[-_\s]', lower_term)
            if words and words[-1] in translations:
                return translations[words[-1]]
        
        # Return original if no translation
        return term


class ModuleInfo:
    """Container for module information."""
    
    def __init__(self, key: str, name: str, prefix: str, endpoints: List[str]):
        self.key = key
        self.name = name
        self.prefix = prefix
        self.endpoints = endpoints
        self.display_name = name  # Can be different from name if translated
    
    def __repr__(self):
        return f"Module({self.name}, prefix={self.prefix}, endpoints={len(self.endpoints)})"