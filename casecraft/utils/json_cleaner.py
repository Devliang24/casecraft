"""JSON cleaning utilities for handling LLM responses."""

import json
import re
from typing import Any, Dict, List, Optional, Union


class JSONCleaner:
    """Clean and repair JSON from LLM responses."""
    
    @staticmethod
    def clean_response(content: str) -> str:
        """Clean raw LLM response to valid JSON.
        
        Args:
            content: Raw response content
            
        Returns:
            Cleaned JSON string
        """
        # Remove leading/trailing whitespace
        content = content.strip()
        
        # Remove markdown code blocks
        content = JSONCleaner._remove_markdown_blocks(content)
        
        # Remove comments
        content = JSONCleaner._remove_comments(content)
        
        # Fix common JSON issues
        content = JSONCleaner._fix_json_issues(content)
        
        # Remove BOM and other special characters
        content = JSONCleaner._remove_special_chars(content)
        
        return content
    
    @staticmethod
    def _remove_markdown_blocks(content: str) -> str:
        """Remove markdown code block markers."""
        # Remove ```json or ``` blocks
        if content.startswith("```"):
            lines = content.split("\n")
            # Find the actual JSON content
            start_idx = 0
            end_idx = len(lines)
            
            for i, line in enumerate(lines):
                if line.strip().startswith("```") and i == 0:
                    start_idx = i + 1
                elif line.strip() == "```" and i > 0:
                    end_idx = i
                    break
            
            content = "\n".join(lines[start_idx:end_idx])
        
        return content
    
    @staticmethod
    def _remove_comments(content: str) -> str:
        """Remove JavaScript-style comments from JSON."""
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        return content
    
    @staticmethod
    def _fix_json_issues(content: str) -> str:
        """Fix common JSON formatting issues."""
        # Fix trailing commas in arrays
        content = re.sub(r',(\s*])', r'\1', content)
        
        # Fix trailing commas in objects
        content = re.sub(r',(\s*})', r'\1', content)
        
        # Fix single quotes (convert to double quotes)
        # This is a simple approach - be careful with strings containing quotes
        content = re.sub(r"'([^']*)'", r'"\1"', content)
        
        # Remove any text before the first [ or {
        match = re.search(r'[\[{]', content)
        if match:
            content = content[match.start():]
        
        # Remove any text after the last ] or }
        for i in range(len(content) - 1, -1, -1):
            if content[i] in ']}':
                content = content[:i + 1]
                break
        
        return content
    
    @staticmethod
    def _remove_special_chars(content: str) -> str:
        """Remove special characters that break JSON parsing."""
        # Remove BOM
        content = content.replace('\ufeff', '')
        
        # Remove zero-width spaces
        content = content.replace('\u200b', '')
        
        # Remove other invisible characters
        content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\r\t')
        
        return content
    
    @staticmethod
    def try_parse_partial(content: str) -> Optional[List[Dict[str, Any]]]:
        """Try to parse partial JSON array, recovering what's possible.
        
        Args:
            content: JSON content that may be truncated
            
        Returns:
            List of successfully parsed objects, or None if failed
        """
        try:
            # First try normal parsing
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try to recover partial array
        if content.startswith('['):
            # Find complete objects
            objects = []
            depth = 0
            current_obj = ""
            in_string = False
            escape_next = False
            
            for i, char in enumerate(content[1:], 1):  # Skip initial [
                if escape_next:
                    escape_next = False
                    current_obj += char
                    continue
                
                if char == '\\' and in_string:
                    escape_next = True
                    current_obj += char
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                
                if not in_string:
                    if char == '{':
                        if depth == 0:
                            current_obj = char
                        else:
                            current_obj += char
                        depth += 1
                    elif char == '}':
                        current_obj += char
                        depth -= 1
                        if depth == 0:
                            # Try to parse this object
                            try:
                                obj = json.loads(current_obj)
                                objects.append(obj)
                                current_obj = ""
                            except:
                                pass
                    elif depth > 0:
                        current_obj += char
                else:
                    if depth > 0:
                        current_obj += char
            
            return objects if objects else None
        
        return None


def clean_json_response(content: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Clean and parse JSON response from LLM.
    
    Args:
        content: Raw LLM response
        
    Returns:
        Parsed JSON object or array
        
    Raises:
        json.JSONDecodeError: If parsing fails after cleaning
    """
    cleaner = JSONCleaner()
    
    # Clean the content
    cleaned = cleaner.clean_response(content)
    
    # Try to parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Try partial recovery for arrays
        if cleaned.startswith('['):
            partial = cleaner.try_parse_partial(cleaned)
            if partial:
                return partial
        
        # Re-raise the error with more context
        raise json.JSONDecodeError(
            f"Failed to parse JSON after cleaning. Original error: {e.msg}",
            e.doc,
            e.pos
        ) from e