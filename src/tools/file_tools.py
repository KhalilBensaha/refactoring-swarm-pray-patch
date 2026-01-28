"""
File Tools - Secure file operations restricted to the sandbox folder.
Implements security: prohibits agents from writing outside the "sandbox" folder.
"""

import os
from pathlib import Path
from typing import List, Optional


class SandboxSecurityError(Exception):
    """Raised when an operation attempts to access files outside the sandbox."""
    pass


def _validate_sandbox_path(filepath: str, sandbox_dir: str) -> Path:
    """
    Validates that a file path is within the sandbox directory.
    
    Args:
        filepath: The file path to validate
        sandbox_dir: The sandbox directory path
        
    Returns:
        The resolved absolute path if valid
        
    Raises:
        SandboxSecurityError: If the path is outside the sandbox
    """
    # Resolve to absolute paths
    sandbox_abs = Path(sandbox_dir).resolve()
    file_abs = Path(filepath).resolve()
    
    # Check if the file is within the sandbox
    try:
        file_abs.relative_to(sandbox_abs)
    except ValueError:
        raise SandboxSecurityError(
            f"🔒 SECURITY VIOLATION: Access denied to '{filepath}'. "
            f"All operations must be within the sandbox: '{sandbox_dir}'"
        )
    
    return file_abs


def read_file_safe(filepath: str, sandbox_dir: str) -> str:
    """
    Safely read a file from within the sandbox directory.
    
    Args:
        filepath: Path to the file to read
        sandbox_dir: The sandbox directory path
        
    Returns:
        The file content as a string
        
    Raises:
        SandboxSecurityError: If trying to read outside sandbox
        FileNotFoundError: If file doesn't exist
    """
    file_abs = _validate_sandbox_path(filepath, sandbox_dir)
    
    if not file_abs.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    with open(file_abs, 'r', encoding='utf-8') as f:
        return f.read()


def write_file_safe(filepath: str, content: str, sandbox_dir: str) -> bool:
    """
    Safely write content to a file within the sandbox directory.
    
    Args:
        filepath: Path to the file to write
        content: Content to write to the file
        sandbox_dir: The sandbox directory path
        
    Returns:
        True if write was successful
        
    Raises:
        SandboxSecurityError: If trying to write outside sandbox
    """
    file_abs = _validate_sandbox_path(filepath, sandbox_dir)
    
    # Create parent directories if they don't exist
    file_abs.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_abs, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True


def list_python_files(sandbox_dir: str) -> List[str]:
    """
    List all Python files in the sandbox directory (recursively).
    
    Args:
        sandbox_dir: The sandbox directory path
        
    Returns:
        List of absolute paths to Python files
    """
    sandbox_path = Path(sandbox_dir).resolve()
    
    if not sandbox_path.exists():
        return []
    
    python_files = []
    for py_file in sandbox_path.rglob("*.py"):
        python_files.append(str(py_file))
    
    return sorted(python_files)


def get_relative_path(filepath: str, sandbox_dir: str) -> str:
    """
    Get the relative path of a file from the sandbox directory.
    
    Args:
        filepath: The absolute file path
        sandbox_dir: The sandbox directory path
        
    Returns:
        The relative path as a string
    """
    sandbox_abs = Path(sandbox_dir).resolve()
    file_abs = Path(filepath).resolve()
    
    try:
        return str(file_abs.relative_to(sandbox_abs))
    except ValueError:
        return filepath
