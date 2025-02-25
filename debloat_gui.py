import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional
import json
import subprocess
from pathlib import Path
from debloat_base import Package, PackageManager, PackageCategory, SafetyStatus, PackageState

class PackageListFrame(ttk.Frame):
    """Frame containing the package list and filter controls"""
    
    def __init__(self, parent: tk.Widget, package_manager: PackageManager) -> None:
        """Initialize the package list frame
        
        Args:
            parent: Parent widget
            package_manager: PackageManager instance
        """
        super().__init__(parent)
        self.package_manager = package_manager
        
        # Filter controls
        filter_frame = ttk.LabelFrame(self, text="Filters")
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Category filter
        ttk.Label(filter_frame, text="Category:").pack(side=tk.LEFT, padx=5)
        self.category_var = tk.StringVar(value="All")
        category_cb = ttk.Combobox(
            filter_frame, 
            textvariable=self.category_var,
            values=["All"] + [c.name for c in PackageCategory]
        )
        category_cb.pack(side=tk.LEFT, padx=5)
        category_cb.bind("<<ComboboxSelected>>", self._apply_filters)
        
        # Safety status filter
        ttk.Label(filter_frame, text="Safety:").pack(side=tk.LEFT, padx=5)
        self.safety_var = tk.StringVar(value="All")
        safety_cb = ttk.Combobox(
            filter_frame,
            textvariable=self.safety_var,
            values=["All"] + [s.name for s in SafetyStatus]
        )
        safety_cb.pack(side=tk.LEFT, padx=5)
        safety_cb.bind("<<ComboboxSelected>>", self._apply_filters)
        
        # Package state filter
        ttk.Label(filter_frame, text="State:").pack(side=tk.LEFT, padx=5)
        self.state_var = tk.StringVar(value="All")
        state_cb = ttk.Combobox(
            filter_frame,
            textvariable=self.state_var,
            values=["All"] + [s.name for s in PackageState]
        )
        state_cb.pack(side=tk.LEFT, padx=5)
        state_cb.bind("<<ComboboxSelected>>", self._apply_filters)
        
        # Search entry
        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filters())
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(
            action_frame,
            text="Remove Selected",
            command=self._remove_selected
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            action_frame,
            text="Restore Selected",
            command=self._restore_selected
        ).pack(side=tk.LEFT, padx=5)
        
        # Package list
        self.tree = ttk.Treeview(
            self,
            columns=("name", "category", "safety", "state"),
            show="headings",
            selectmode="extended"
        )
        
        # Configure columns
        self.tree.heading("name", text="Package Name", command=lambda: self._sort_column("name"))
        self.tree.heading("category", text="Category", command=lambda: self._sort_column("category"))
        self.tree.heading("safety", text="Safety", command=lambda: self._sort_column("safety"))
        self.tree.heading("state", text="State", command=lambda: self._sort_column("state"))
        
        self.tree.column("name", width=300)
        self.tree.column("category", width=100)
        self.tree.column("safety", width=100)
        self.tree.column("state", width=100)
        
        # Bind tooltip events
        self.tooltip = None
        self.tree.bind("<Motion>", self._show_tooltip)
        self.tree.bind("<Leave>", self._hide_tooltip)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack list and scrollbar
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Bind double-click to show details
        self.tree.bind("<Double-1>", self._show_package_details)
        
        # Load initial data
        self._load_packages()
        
    def _show_tooltip(self, event) -> None:
        """Show tooltip with package description on hover"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
            
        # Get package info
        pkg_name = self.tree.item(item)["values"][0]
        pkg = self.package_manager.packages[pkg_name]
        
        # Create tooltip if description exists
        if not pkg.description:
            return
            
        # Hide existing tooltip
        self._hide_tooltip(None)
        
        # Get item bbox
        bbox = self.tree.bbox(item)
        if not bbox:
            return  # Item not visible
            
        # Create new tooltip
        self.tooltip = tk.Toplevel()
        self.tooltip.wm_overrideredirect(True)
        
        # Position tooltip near cursor
        x = event.x_root + 10
        y = event.y_root + 10
        self.tooltip.wm_geometry(f"+{x}+{y}")
        
        # Create tooltip content
        label = ttk.Label(
            self.tooltip,
            text=pkg.description,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            wraplength=400  # Wrap long descriptions
        )
        label.pack(padx=5, pady=5)
    
    def _hide_tooltip(self, event) -> None:
        """Hide the tooltip window"""
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None
    
    def _load_packages(self) -> None:
        """Load packages into the treeview"""
        self.tree.delete(*self.tree.get_children())
        for pkg in self.package_manager.packages.values():
            self.tree.insert(
                "",
                tk.END,
                values=(
                    pkg.name,
                    pkg.category.name,
                    pkg.safety_status.name,
                    pkg.state.name
                )
            )
    
    def _apply_filters(self, *args) -> None:
        """Apply current filters to package list"""
        self.tree.delete(*self.tree.get_children())
        
        category_filter = self.category_var.get()
        safety_filter = self.safety_var.get()
        state_filter = self.state_var.get()
        search_text = self.search_var.get().lower()
        
        for pkg in self.package_manager.packages.values():
            if (category_filter == "All" or pkg.category.name == category_filter) and \
               (safety_filter == "All" or pkg.safety_status.name == safety_filter) and \
               (state_filter == "All" or pkg.state.name == state_filter) and \
               (search_text in pkg.name.lower() or search_text in pkg.description.lower()):
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        pkg.name,
                        pkg.category.name,
                        pkg.safety_status.name,
                        pkg.state.name
                    )
                )
    
    def _sort_column(self, column: str) -> None:
        """Sort treeview by column
        
        Args:
            column: Column identifier to sort by
        """
        items = [(self.tree.set(item, column), item) for item in self.tree.get_children("")]
        items.sort()
        
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)
    
    def _show_package_details(self, event) -> None:
        """Show details for selected package"""
        selection = self.tree.selection()
        if not selection:
            return
            
        item = selection[0]
        pkg_name = self.tree.item(item)["values"][0]
        pkg = self.package_manager.packages[pkg_name]
        
        details = tk.Toplevel(self)
        details.title(f"Package Details: {pkg.name}")
        details.geometry("600x400")
        
        # Package info
        info_frame = ttk.LabelFrame(details, text="Package Information")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(info_frame, text=f"Name: {pkg.name}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Description: {pkg.description}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Category: {pkg.category.name}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Safety Status: {pkg.safety_status.name}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Current State: {pkg.state.name}").pack(anchor=tk.W)
        
        # Dependencies
        if pkg.dependencies:
            dep_frame = ttk.LabelFrame(details, text="Dependencies")
            dep_frame.pack(fill=tk.X, padx=5, pady=5)
            for dep in pkg.dependencies:
                ttk.Label(dep_frame, text=dep).pack(anchor=tk.W)
        
        # Dependents
        if pkg.dependents:
            dep_frame = ttk.LabelFrame(details, text="Dependent Packages")
            dep_frame.pack(fill=tk.X, padx=5, pady=5)
            for dep in pkg.dependents:
                ttk.Label(dep_frame, text=dep).pack(anchor=tk.W)
        
        # Action buttons
        button_frame = ttk.Frame(details)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        if pkg.state == PackageState.INSTALLED:
            ttk.Button(
                button_frame,
                text="Remove Package",
                command=lambda: self._remove_package(pkg)
            ).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Button(
                button_frame,
                text="Restore Package",
                command=lambda: self._restore_package(pkg)
            ).pack(side=tk.LEFT, padx=5)
    
    def _remove_package(self, pkg: Package) -> None:
        """Remove selected package
        
        Args:
            pkg: Package to remove
        """
        if messagebox.askyesno(
            "Confirm Removal",
            f"Are you sure you want to remove {pkg.name}?\n\n" +
            "This will uninstall the package from your device."
        ):
            if self.package_manager.remove_package(pkg.name):
                messagebox.showinfo("Success", f"Package {pkg.name} removed successfully")
                self._load_packages()
            else:
                messagebox.showerror("Error", f"Failed to remove package {pkg.name}")
    
    def _remove_selected(self) -> None:
        """Remove all selected packages"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "No packages selected")
            return
            
        # Get selected packages
        packages = []
        for item in selection:
            pkg_name = self.tree.item(item)["values"][0]
            pkg = self.package_manager.packages[pkg_name]
            if pkg.safety_status == SafetyStatus.ESSENTIAL:
                messagebox.showwarning(
                    "Warning",
                    f"Cannot remove essential package: {pkg_name}"
                )
                return
            packages.append(pkg)
            
        # Confirm removal
        if not messagebox.askyesno(
            "Confirm Removal",
            f"Remove {len(packages)} selected packages?\n\n" +
            "This will uninstall these packages from your device."
        ):
            return
            
        # Remove packages
        success = []
        failed = []
        for pkg in packages:
            if self.package_manager.remove_package(pkg.name):
                success.append(pkg.name)
            else:
                failed.append(pkg.name)
                
        # Show results
        message = f"Successfully removed {len(success)} packages"
        if failed:
            message += f"\nFailed to remove {len(failed)} packages"
            
        if success:
            messagebox.showinfo("Operation Complete", message)
        else:
            messagebox.showerror("Operation Failed", message)
            
        self._load_packages()
    
    def _restore_selected(self) -> None:
        """Restore all selected packages"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "No packages selected")
            return
            
        # Get selected packages
        packages = []
        for item in selection:
            pkg_name = self.tree.item(item)["values"][0]
            pkg = self.package_manager.packages[pkg_name]
            if pkg.state != PackageState.REMOVED:
                messagebox.showwarning(
                    "Warning",
                    f"Package not removed: {pkg_name}"
                )
                return
            packages.append(pkg)
            
        # Confirm restoration
        if not messagebox.askyesno(
            "Confirm Restore",
            f"Restore {len(packages)} selected packages?"
        ):
            return
            
        # Restore packages
        success = []
        failed = []
        for pkg in packages:
            if self.package_manager.restore_package(pkg.name):
                success.append(pkg.name)
            else:
                failed.append(pkg.name)
                
        # Show results
        message = f"Successfully restored {len(success)} packages"
        if failed:
            message += f"\nFailed to restore {len(failed)} packages"
            
        if success:
            messagebox.showinfo("Operation Complete", message)
        else:
            messagebox.showerror("Operation Failed", message)
            
        self._load_packages()
    
    def _restore_package(self, pkg: Package) -> None:
        """Restore selected package
        
        Args:
            pkg: Package to restore
        """
        if messagebox.askyesno(
            "Confirm Restore",
            f"Are you sure you want to restore {pkg.name}?"
        ):
            if self.package_manager.restore_package(pkg.name):
                messagebox.showinfo("Success", f"Package {pkg.name} restored successfully")
                self._load_packages()
            else:
                messagebox.showerror("Error", f"Failed to restore package {pkg.name}")


class DebloatGUI:
    """Main GUI application for package management"""
    
    def __init__(self) -> None:
        """Initialize the GUI application"""
        self.root = tk.Tk()
        self.root.title("Android Package Manager")
        self.root.geometry("800x600")
        
        # Initialize package manager
        self.package_manager = PackageManager()
        
        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Device connection status
        self.connection_var = tk.StringVar(value="No device connected")
        connection_label = ttk.Label(
            toolbar,
            textvariable=self.connection_var,
            foreground="red"
        )
        connection_label.pack(side=tk.LEFT, padx=5)
        
        # Refresh button
        refresh_btn = ttk.Button(
            toolbar,
            text="Refresh Device",
            command=self._refresh_device
        )
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Scan packages button
        scan_btn = ttk.Button(
            toolbar,
            text="Scan Packages",
            command=self._scan_packages
        )
        scan_btn.pack(side=tk.LEFT, padx=5)
        
        # Add package list
        self.package_list = PackageListFrame(main_frame, self.package_manager)
        self.package_list.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(fill=tk.X)
        
        # Check initial device connection
        self._check_device_connection()
    
    def _check_device_connection(self) -> bool:
        """Check if an Android device is connected
        
        Returns:
            True if device connected, False otherwise
        """
        try:
            # First check if adb is available
            try:
                subprocess.run(['adb', 'version'], capture_output=True, check=True)
            except FileNotFoundError:
                self.connection_var.set("ADB not found in PATH")
                return False
            except subprocess.CalledProcessError:
                self.connection_var.set("ADB error")
                return False
                
            # Check for connected devices
            output = self.package_manager._execute_adb(['devices'])
            devices = [
                line.split()[0] for line in output.splitlines()[1:]
                if line.strip() and not line.strip().startswith('*')
            ]
            
            if devices:
                self.connection_var.set(f"Connected: {devices[0]}")
                return True
            else:
                self.connection_var.set("No device connected")
                return False
                
        except subprocess.CalledProcessError as e:
            self.connection_var.set(f"ADB error: {str(e)}")
            return False
        except Exception as e:
            self.connection_var.set(f"Error: {str(e)}")
            return False
    
    def _refresh_device(self) -> None:
        """Refresh device connection status"""
        if self._check_device_connection():
            messagebox.showinfo("Success", "Device connected successfully")
        else:
            error_msg = "Error: "
            if "ADB not found" in self.connection_var.get():
                error_msg += "ADB is not installed or not in PATH. Please install Android Debug Bridge."
            elif "No device" in self.connection_var.get():
                error_msg += "No device found. Please check:\n" + \
                           "1. USB connection\n" + \
                           "2. USB debugging is enabled on device\n" + \
                           "3. Device is authorized for debugging"
            else:
                error_msg += self.connection_var.get()
                
            messagebox.showerror("Connection Error", error_msg)
    
    def _scan_packages(self) -> None:
        """Scan connected device for installed packages"""
        if not self._check_device_connection():
            messagebox.showerror("Error", "No device connected")
            return
            
        try:
            installed_packages = self.package_manager.get_installed_packages()
            
            # Package scanning and state determination is now handled by get_installed_packages()
            # We don't need to modify packages here as they're already properly updated
            
            # Save updated package database
            self.package_manager.save_package_db()
            
            # Write scan results to file
            self._write_scan_results(installed_packages)
            
            # Refresh display
            self.package_list._load_packages()
            self._update_status()
            
            messagebox.showinfo(
                "Success",
                f"Found {len(installed_packages)} installed packages"
            )
            
        except subprocess.CalledProcessError as e:
            messagebox.showerror(
                "Error",
                f"Failed to scan packages: {str(e)}"
            )
    
    def _write_scan_results(self, installed_packages: List[str]) -> None:
        """Write scan results to output file
        
        Args:
            installed_packages: List of package names found on device
        """
        from datetime import datetime
        
        output = []
        output.append("# Android Package Scan Results\n")
        output.append(f"Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output.append(f"Total Packages Found: {len(installed_packages)}\n\n")
        
        # Group packages by category
        packages_by_category = {}
        for pkg_name in installed_packages:
            pkg = self.package_manager.packages[pkg_name]
            if pkg.category not in packages_by_category:
                packages_by_category[pkg.category] = []
            packages_by_category[pkg.category].append(pkg)
        
        # Write packages grouped by category
        for category in sorted(packages_by_category.keys(), key=lambda x: x.name):
            output.append(f"## {category.name}\n")
            for pkg in sorted(packages_by_category[category], key=lambda x: x.name):
                output.append(f"- {pkg.name}\n")
                output.append(f"  - Description: {pkg.description}\n")
                output.append(f"  - Safety Status: {pkg.safety_status.name}\n")
                output.append(f"  - State: {pkg.state.name}\n")
            output.append("\n")
            
        # Write to file
        with open("./phone_debloat/output1.md", "w") as f:
            f.writelines(output)
    
    def _update_status(self) -> None:
        """Update status bar with package counts"""
        total = len(self.package_manager.packages)
        removed = len(self.package_manager.get_removed_packages())
        self.status_var.set(
            f"Total Packages: {total} | " +
            f"Removed: {removed} | " +
            f"Installed: {total - removed}"
        )
    
    def run(self) -> None:
        """Start the GUI application"""
        self.root.mainloop()


if __name__ == "__main__":
    app = DebloatGUI()
    app.run()
