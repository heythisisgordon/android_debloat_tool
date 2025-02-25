from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional
import json
import subprocess
from pathlib import Path


class PackageCategory(Enum):
    """Categories for Android packages"""
    SYSTEM = auto()
    SAMSUNG = auto()
    GOOGLE = auto()
    CARRIER = auto()
    THIRD_PARTY = auto()
    UNKNOWN = auto()


class SafetyStatus(Enum):
    """Safety status for package removal"""
    SAFE_TO_REMOVE = auto()
    ESSENTIAL = auto()
    CAUTION = auto()  # Removal may impact some features
    UNKNOWN = auto()


class PackageState(Enum):
    """Current state of a package"""
    INSTALLED = auto()
    REMOVED = auto()
    DISABLED = auto()


@dataclass
class Package:
    """Represents an Android package with metadata"""
    name: str  # Package identifier (e.g. com.samsung.android.app.camera)
    description: str
    category: PackageCategory
    safety_status: SafetyStatus
    state: PackageState
    dependencies: List[str] = None  # List of package names this package depends on
    dependents: List[str] = None    # List of package names that depend on this package
    
    def __post_init__(self) -> None:
        """Initialize optional fields"""
        if self.dependencies is None:
            self.dependencies = []
        if self.dependents is None:
            self.dependents = []


class PackageManager:
    """Manages Android packages via ADB"""
    
    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize the package manager
        
        Args:
            db_path: Path to package database JSON file
        """
        self.packages: Dict[str, Package] = {}
        self.db_path = db_path or Path("package_db.json")
        self.reference_data: Dict[str, Dict[str, str]] = {}
        self._load_reference_data()
        self._load_package_db()
        
    def _load_reference_data(self) -> None:
        """Load package descriptions from references.md"""
        try:
            with open("phone_debloat/references.md", 'r') as f:
                # Skip header line and parse tab-separated data
                for line in f.readlines()[1:]:
                    parts = [p.strip() for p in line.split('\t')]
                    if len(parts) >= 4 and parts[1]:  # Has package name
                        self.reference_data[parts[1]] = {
                            'name': parts[0],
                            'description': parts[2],  # Extra Information column
                            'safe': parts[3]
                        }
        except FileNotFoundError:
            print("Warning: references.md not found")
            
    def _get_package_description(self, package_name: str) -> str:
        """Get package description from reference data
        
        Args:
            package_name: Package identifier
            
        Returns:
            Package description string
        """
        if package_name in self.reference_data:
            return self.reference_data[package_name]['description']
        return ""
        
    def _classify_safety(self, package_name: str) -> SafetyStatus:
        """Determine package safety status based on known patterns
        
        Args:
            package_name: Package identifier
            
        Returns:
            SafetyStatus enum value
        """
        # Check reference data first
        if package_name in self.reference_data:
            safe_value = self.reference_data[package_name]['safe'].upper()
            if safe_value == 'NO':
                return SafetyStatus.ESSENTIAL
            elif safe_value == 'NOT RECOMMENDED':
                return SafetyStatus.CAUTION
            elif safe_value == 'YES':
                return SafetyStatus.SAFE_TO_REMOVE
        
        # Known essential packages
        essential_patterns = [
            "com.samsung.android.kgclient",  # Knox - DO NOT DISABLE
            "com.android.phone",             # Phone functionality
            "com.android.systemui",          # System UI
            "com.android.settings",          # Settings app
            "com.android.providers.settings" # Settings provider
        ]
        
        # Known caution packages
        caution_patterns = [
            "com.android.mms",              # MMS functionality
            "com.samsung.advp.imssettings", # IMS Settings
            ".knox.",                       # Knox security features
            "com.samsung.android.messaging" # Default messaging
        ]
        
        # Check for exact matches first
        if any(package_name == pattern for pattern in essential_patterns):
            return SafetyStatus.ESSENTIAL
            
        if any(package_name == pattern for pattern in caution_patterns):
            return SafetyStatus.CAUTION
            
        # Check for pattern matches
        if any(pattern in package_name for pattern in [
            "provider",      # Content providers
            "security",      # Security features
            "permission",    # Permission handlers
            "system",        # System components
            "framework"      # Framework components
        ]):
            return SafetyStatus.CAUTION
            
        # Common safe-to-remove patterns
        if any(pattern in package_name for pattern in [
            "facebook",
            "game",
            "theme",
            "wallpaper",
            "sticker",
            "widget",
            "overlay",
            "demo",
            "test",
            "sample",
            "bixby",
            "ar",           # AR features
            "edge",         # Edge panels
            "share"         # Sharing features
        ]):
            return SafetyStatus.SAFE_TO_REMOVE
            
        return SafetyStatus.UNKNOWN
        
    def _classify_category(self, package_name: str) -> PackageCategory:
        """Determine package category based on package name
        
        Args:
            package_name: Package identifier
            
        Returns:
            PackageCategory enum value
        """
        if package_name.startswith("com.samsung."):
            return PackageCategory.SAMSUNG
        elif package_name.startswith("com.sec."):  # Samsung's other namespace
            return PackageCategory.SAMSUNG
        elif package_name.startswith("com.google."):
            return PackageCategory.GOOGLE
        elif package_name.startswith("com.android."):
            return PackageCategory.SYSTEM
        elif any(package_name.startswith(prefix) for prefix in [
            "com.verizon.",
            "com.vzw.",
            "com.att.",
            "com.sprint.",
            "com.tmobile."
        ]):
            return PackageCategory.CARRIER
        elif any(package_name.startswith(prefix) for prefix in [
            "com.facebook.",
            "com.microsoft.",
            "com.spotify.",
            "com.netflix.",
            "com.amazon."
        ]):
            return PackageCategory.THIRD_PARTY
            
        return PackageCategory.UNKNOWN

    def _load_package_db(self) -> None:
        """Load package definitions from JSON database"""
        if self.db_path.exists():
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                for pkg_data in data:
                    pkg = Package(
                        name=pkg_data['name'],
                        description=pkg_data['description'],
                        category=PackageCategory[pkg_data['category']],
                        safety_status=SafetyStatus[pkg_data['safety_status']],
                        state=PackageState[pkg_data['state']],
                        dependencies=pkg_data.get('dependencies', []),
                        dependents=pkg_data.get('dependents', [])
                    )
                    self.packages[pkg.name] = pkg

    def save_package_db(self) -> None:
        """Save current package definitions to JSON database"""
        data = []
        for pkg in self.packages.values():
            pkg_data = {
                'name': pkg.name,
                'description': pkg.description,
                'category': pkg.category.name,
                'safety_status': pkg.safety_status.name,
                'state': pkg.state.name,
                'dependencies': pkg.dependencies,
                'dependents': pkg.dependents
            }
            data.append(pkg_data)
            
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _execute_adb(self, command: List[str]) -> str:
        """Execute an ADB command and return the output
        
        Args:
            command: List of command components
            
        Returns:
            Command output as string
            
        Raises:
            subprocess.CalledProcessError: If command fails
        """
        try:
            result = subprocess.run(
                ['adb'] + command,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"ADB command failed: {e.stderr}")
            raise

    def get_installed_packages(self) -> List[str]:
        """Get list of all packages from device, including uninstalled and disabled
        
        Returns:
            List of package names
        """
        # Get packages in each state explicitly
        enabled = self._execute_adb(['shell', 'pm', 'list', 'packages', '-e'])  # Only enabled packages
        disabled = self._execute_adb(['shell', 'pm', 'list', 'packages', '-d'])  # Only disabled packages
        uninstalled = self._execute_adb(['shell', 'pm', 'list', 'packages', '-u'])  # Only uninstalled packages
        
        # Helper function to extract package names from adb output
        def extract_packages(output: str) -> set[str]:
            return {line.split(':', 1)[1].strip() 
                   for line in output.splitlines() 
                   if ':' in line}
        
        # Get sets of packages in each state
        enabled_pkgs = extract_packages(enabled)
        disabled_pkgs = extract_packages(disabled)
        uninstalled_pkgs = extract_packages(uninstalled)
        
        # Combine all unique packages
        all_pkgs = enabled_pkgs | disabled_pkgs | uninstalled_pkgs
        
        # Process each package
        for pkg_name in all_pkgs:
            # Determine state by checking which list it appears in
            if pkg_name in enabled_pkgs:
                state = PackageState.INSTALLED
            elif pkg_name in disabled_pkgs:
                state = PackageState.DISABLED
            else:
                state = PackageState.REMOVED
            
            if pkg_name not in self.packages:
                # Create new package
                pkg = Package(
                    name=pkg_name,
                    description=self._get_package_description(pkg_name),
                    category=self._classify_category(pkg_name),
                    safety_status=self._classify_safety(pkg_name),
                    state=state
                )
                self.packages[pkg_name] = pkg
            else:
                # Update existing package
                pkg = self.packages[pkg_name]
                pkg.description = self._get_package_description(pkg_name)
                pkg.category = self._classify_category(pkg_name)
                pkg.safety_status = self._classify_safety(pkg_name)
                pkg.state = state
                
        # Save changes to database
        self.save_package_db()
        return list(all_pkgs)

    def remove_package(self, package_name: str) -> bool:
        """Remove a package from the device
        
        Args:
            package_name: Name of package to remove
            
        Returns:
            True if removal successful, False otherwise
        """
        if package_name not in self.packages:
            print(f"Unknown package: {package_name}")
            return False
            
        pkg = self.packages[package_name]
        
        # Safety checks
        if pkg.safety_status == SafetyStatus.ESSENTIAL:
            print(f"Cannot remove essential package: {package_name}")
            return False
            
        if pkg.dependents:
            print(f"Package has dependents: {pkg.dependents}")
            return False
            
        try:
            self._execute_adb(['shell', 'pm', 'uninstall', '-k', '--user', '0', package_name])
            pkg.state = PackageState.REMOVED
            self.save_package_db()
            return True
        except subprocess.CalledProcessError:
            return False

    def restore_package(self, package_name: str) -> bool:
        """Restore a previously removed package
        
        Args:
            package_name: Name of package to restore
            
        Returns:
            True if restore successful, False otherwise
        """
        if package_name not in self.packages:
            print(f"Unknown package: {package_name}")
            return False
            
        try:
            self._execute_adb(['shell', 'cmd', 'package', 'install-existing', package_name])
            self.packages[package_name].state = PackageState.INSTALLED
            self.save_package_db()
            return True
        except subprocess.CalledProcessError:
            return False

    def get_removable_packages(self) -> List[Package]:
        """Get list of packages that are safe to remove
        
        Returns:
            List of Package objects
        """
        return [
            pkg for pkg in self.packages.values()
            if pkg.safety_status == SafetyStatus.SAFE_TO_REMOVE
            and pkg.state == PackageState.INSTALLED
            and not pkg.dependents
        ]

    def get_removed_packages(self) -> List[Package]:
        """Get list of packages that have been removed
        
        Returns:
            List of Package objects
        """
        return [
            pkg for pkg in self.packages.values()
            if pkg.state == PackageState.REMOVED
        ]
