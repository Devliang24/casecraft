"""
Priority assigner for test cases.
Assigns P0/P1/P2 priorities based on position without any hardcoding.
"""

from typing import List, Dict, Any
from collections import defaultdict


class PriorityAssigner:
    """Assigns priorities to test cases based on their relative importance."""
    
    def __init__(self):
        """Initialize the priority assigner."""
        # Priority distribution ratios (can be configured)
        self.p0_ratio = 0.3  # Top 30% are P0
        self.p1_ratio = 0.4  # Next 40% are P1
        self.p2_ratio = 0.3  # Bottom 30% are P2
    
    def assign_priorities(self, test_cases: List[Any]) -> List[Any]:
        """
        Assign priorities to test cases based on their position and test type.
        
        This method groups test cases by type and assigns priorities based on
        their position within each group. No hardcoded keywords or paths are used.
        
        Args:
            test_cases: List of test case objects with test_type attribute
            
        Returns:
            List of test cases with priority field assigned
        """
        if not test_cases:
            return test_cases
        
        # Group test cases by test type
        grouped = self._group_by_test_type(test_cases)
        
        # Assign priorities within each group
        for test_type, cases in grouped.items():
            self._assign_priorities_to_group(cases)
        
        return test_cases
    
    def _group_by_test_type(self, test_cases: List[Any]) -> Dict[str, List[Any]]:
        """
        Group test cases by their test type.
        
        Args:
            test_cases: List of test case objects
            
        Returns:
            Dictionary mapping test type to list of test cases
        """
        grouped = defaultdict(list)
        
        for tc in test_cases:
            # Get test type, default to 'unknown' if not present
            test_type = getattr(tc, 'test_type', 'unknown')
            if hasattr(test_type, 'value'):  # Handle enum types
                test_type = test_type.value
            grouped[str(test_type).lower()].append(tc)
        
        return grouped
    
    def _assign_priorities_to_group(self, cases: List[Any]) -> None:
        """
        Assign priorities to a group of test cases based on position.
        
        The first cases (assumed to be most important) get P0,
        middle cases get P1, and last cases get P2.
        
        Args:
            cases: List of test cases in the same group
        """
        if not cases:
            return
        
        total = len(cases)
        
        # Calculate boundaries
        # Ensure at least 1 case in each priority level if we have >= 3 cases
        if total >= 3:
            p0_count = max(1, int(total * self.p0_ratio))
            p1_count = max(1, int(total * self.p1_ratio))
            # P2 gets the rest
            p2_count = total - p0_count - p1_count
            
            # Adjust if p2_count is 0 or negative
            if p2_count <= 0:
                p2_count = 1
                # Reduce p1_count if needed
                if p0_count + p1_count + p2_count > total:
                    p1_count = total - p0_count - p2_count
                    if p1_count <= 0:
                        # For very small groups, distribute evenly
                        p0_count = 1
                        p1_count = 1
                        p2_count = total - 2
        elif total == 2:
            # For 2 cases: 1 P0, 1 P1
            p0_count = 1
            p1_count = 1
            p2_count = 0
        else:
            # For 1 case: it's P0
            p0_count = 1
            p1_count = 0
            p2_count = 0
        
        # Assign priorities based on position
        for i, tc in enumerate(cases):
            if i < p0_count:
                priority = "P0"
            elif i < p0_count + p1_count:
                priority = "P1"
            else:
                priority = "P2"
            
            # Set priority attribute
            if hasattr(tc, 'priority'):
                tc.priority = priority
            else:
                setattr(tc, 'priority', priority)
    
    def get_priority_distribution(self, test_cases: List[Any]) -> Dict[str, Dict[str, int]]:
        """
        Get the distribution of priorities across test types.
        
        Args:
            test_cases: List of test cases with priorities assigned
            
        Returns:
            Dictionary showing count of each priority level per test type
        """
        distribution = defaultdict(lambda: defaultdict(int))
        
        for tc in test_cases:
            test_type = getattr(tc, 'test_type', 'unknown')
            if hasattr(test_type, 'value'):
                test_type = test_type.value
            test_type = str(test_type).lower()
            
            priority = getattr(tc, 'priority', 'unassigned')
            distribution[test_type][priority] += 1
        
        return dict(distribution)
    
    def validate_distribution(self, test_cases: List[Any]) -> bool:
        """
        Validate that each test type has appropriate priority distribution.
        
        Args:
            test_cases: List of test cases with priorities assigned
            
        Returns:
            True if distribution is valid, False otherwise
        """
        distribution = self.get_priority_distribution(test_cases)
        
        for test_type, priorities in distribution.items():
            # Check that we have at least one P0 for each test type
            if priorities.get('P0', 0) == 0 and sum(priorities.values()) > 0:
                return False
            
            # If we have 3+ cases, we should have all three priority levels
            total = sum(priorities.values())
            if total >= 3:
                if priorities.get('P0', 0) == 0 or priorities.get('P1', 0) == 0:
                    return False
        
        return True