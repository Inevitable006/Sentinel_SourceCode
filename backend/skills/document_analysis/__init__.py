"""
Skill: document_analysis
Reads and extracts text from local files (TXT, CSV, JSON, MD) with strict path containment.
Risk Tier: 2 (requires user confirmation for privacy)
Capabilities: None
"""
import os
from pathlib import Path
from app.core.paths import SENTINEL_DATA_DIR

# The root directory of the project
PROJECT_ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "../../../"))).resolve()

# Allowed directories for reading files
ALLOWED_DIRECTORIES = [
    PROJECT_ROOT,
    SENTINEL_DATA_DIR
]

def _is_path_contained(child: str, allowed_parents: list[Path]) -> bool:
    """Case-insensitive, symlink-resolving containment check against multiple parents."""
    try:
        child_resolved = Path(os.path.realpath(child)).resolve()
        for parent in allowed_parents:
            parent_resolved = parent.resolve()
            try:
                child_resolved.relative_to(parent_resolved)
                return True
            except ValueError:
                continue
        return False
    except (ValueError, OSError):
        return False

def read_document(file_path: str) -> str:
    """
    Reads the content of a local file safely.
    Enforces canonical path containment and output truncation (10KB limit).
    """
    if not _is_path_contained(file_path, ALLOWED_DIRECTORIES):
        return f"Security Error: Path traversal blocked. The file '{file_path}' is outside the allowed safe directories."
        
    if not os.path.isfile(file_path):
        return f"Error: File not found or is not a regular file: {file_path}"
        
    try:
        # Detect encoding simply by trying utf-8 then falling back to latin-1
        content = ""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read(10240 + 1) # Read up to limit + 1 to detect truncation
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read(10240 + 1)
                
        if len(content) > 10240:
            return content[:10240] + "\n... [TRUNCATED: Output exceeded 10KB limit]"
            
        return content
    except Exception as e:
        return f"System Error reading document: {str(e)}"
