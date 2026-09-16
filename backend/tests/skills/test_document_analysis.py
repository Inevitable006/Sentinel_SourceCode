import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from app.core.paths import SENTINEL_DATA_DIR
from skills.document_analysis import read_document

class TestDocumentAnalysis:

    def test_read_document_success(self):
        # Create a temp file inside SENTINEL_DATA_DIR (which is an allowed path)
        safe_dir = SENTINEL_DATA_DIR / "test_docs"
        safe_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = safe_dir / "safe_file.txt"
        test_file.write_text("Hello Sentinel", encoding="utf-8")
        
        try:
            result = read_document(str(test_file))
            assert "Hello Sentinel" in result
        finally:
            if test_file.exists():
                test_file.unlink()
                
    def test_read_document_truncation(self):
        safe_dir = SENTINEL_DATA_DIR / "test_docs"
        safe_dir.mkdir(parents=True, exist_ok=True)
        
        test_file = safe_dir / "large_file.txt"
        test_file.write_text("A" * 15000, encoding="utf-8")
        
        try:
            result = read_document(str(test_file))
            assert "TRUNCATED: Output exceeded 10KB limit" in result
            assert len(result) < 11000
        finally:
            if test_file.exists():
                test_file.unlink()
                
    def test_path_traversal_blocked(self):
        # Attempt to read a file outside the allowed directories
        # We can test with a known file like C:\Windows\win.ini on Windows or /etc/passwd on Linux
        # But a robust test just creates a temp file completely outside the project
        
        with NamedTemporaryFile(delete=False) as tf:
            tf.write(b"Secret data")
            tf.flush()
            unsafe_path = tf.name
            
        try:
            result = read_document(unsafe_path)
            assert "Security Error: Path traversal blocked" in result
        finally:
            os.remove(unsafe_path)
            
    def test_file_not_found(self):
        safe_dir = SENTINEL_DATA_DIR / "test_docs"
        safe_dir.mkdir(parents=True, exist_ok=True)
        
        missing_file = safe_dir / "does_not_exist_404.txt"
        
        result = read_document(str(missing_file))
        assert "Error: File not found" in result
