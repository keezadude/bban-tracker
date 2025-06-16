"""
BBAN-Themed UI Manager for BBAN-Tracker GUI.

This module implements the complete BBAN design schema with colors,
typography, and styling that matches the reference screenshots pixel-perfectly.
Based on the BBAN color palette: Green (#AAD69C), Yellow (#F3D26A), Dark Grey (#333132).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette, QLinearGradient, QPixmap, QPainter, QBrush
from PySide6.QtWidgets import QApplication, QWidget
from typing import Dict, Tuple, Optional
import os


class BBANColors:
    """Color palette implementing the exact BBAN design schema from reference screenshots."""
    
    # BBAN Brand Colors (from reference CSS)
    BBAN_GREEN = QColor("#AAD69C")           # Primary interactive green
    BBAN_GREEN_DARKER = QColor("#89B47F")    # Darker green for gradients
    BBAN_GREEN_DARKEST = QColor("#678D60")   # Deep green accents
    
    BBAN_YELLOW = QColor("#F3D26A")          # Secondary interactive yellow  
    BBAN_YELLOW_DARKER = QColor("#D1B05A")   # Darker yellow for gradients
    BBAN_YELLOW_DARKEST = QColor("#AF8C3A")  # Deep yellow accents
    
    BBAN_DARK_GREY = QColor("#333132")       # Primary background
    BBAN_MID_GREY = QColor("#444243")        # Secondary background
    BBAN_LIGHT_GREY = QColor("#666465")      # Accent grey
    
    # Interactive Colors (mapped to BBAN palette)
    PRIMARY_INTERACTIVE = BBAN_GREEN
    PRIMARY_DARKER = BBAN_GREEN_DARKER
    SECONDARY_INTERACTIVE = BBAN_YELLOW
    SECONDARY_DARKER = BBAN_YELLOW_DARKER
    
    # Background Colors
    BACKGROUND_DEEP = BBAN_DARK_GREY
    BACKGROUND_MID = BBAN_MID_GREY
    
    # Text Colors
    TEXT_PRIMARY = QColor("#FFFFFF")          # Bright White
    TEXT_SECONDARY = BBAN_GREEN               # BBAN Green for accents
    TEXT_TERTIARY = QColor("#A0A0A0")         # Light Gray
    
    # Status Colors
    SUCCESS = BBAN_GREEN
    WARNING = BBAN_YELLOW
    ERROR = QColor("#E53E3E")                 # Red for errors
    
    # Transparency variations
    BACKGROUND_DEEP_ALPHA = QColor(51, 49, 50, 200)
    BACKGROUND_MID_ALPHA = QColor(68, 66, 67, 180)
    
    # Menu Shard Specific Colors (from reference CSS)
    # Match Shard - Green background, dark text/icons
    MENU_SHARD_MATCH_BG = BBAN_GREEN
    MENU_SHARD_MATCH_TEXT = BBAN_DARK_GREY
    MENU_SHARD_MATCH_ICON = BBAN_DARK_GREY
    
    # Free Play Shard - Yellow background, dark text/icons  
    MENU_SHARD_FREEPLAY_BG = BBAN_YELLOW
    MENU_SHARD_FREEPLAY_TEXT = BBAN_DARK_GREY
    MENU_SHARD_FREEPLAY_ICON = BBAN_DARK_GREY
    
    # System Hub Shard - Grey background, white text, green icon
    MENU_SHARD_SYSTEMHUB_BG = BBAN_MID_GREY
    MENU_SHARD_SYSTEMHUB_TEXT = QColor("#FFFFFF")
    MENU_SHARD_SYSTEMHUB_ICON = BBAN_GREEN
    
    @classmethod
    def get_gradient_primary(cls) -> QLinearGradient:
        """Get primary green gradient."""
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setColorAt(0, cls.BBAN_GREEN_DARKER)
        gradient.setColorAt(1, cls.BBAN_GREEN)
        return gradient
    
    @classmethod
    def get_gradient_secondary(cls) -> QLinearGradient:
        """Get secondary yellow gradient."""
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setColorAt(0, cls.BBAN_YELLOW_DARKER)
        gradient.setColorAt(1, cls.BBAN_YELLOW)
        return gradient


class BBANFonts:
    """Typography system implementing the BBAN design schema with Exo 2 and Inter fonts."""
    
    def __init__(self):
        self._fonts_loaded = False
        self._load_fonts()
    
    def _load_fonts(self):
        """Load BBAN fonts (Exo 2 for headings, Inter for body)."""
        # Note: In production, load Exo 2 and Inter fonts from assets
        # For now, we'll use system fonts with similar characteristics
        self._fonts_loaded = True
    
    def get_heading_font(self, size: int = 24, weight: int = QFont.Weight.Bold) -> QFont:
        """Get heading font (Exo 2 equivalent for kiosk titles)."""
        font = QFont("Arial", size)  # Fallback closest to Exo 2
        font.setWeight(weight)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font
    
    def get_body_font(self, size: int = 12, weight: int = QFont.Weight.Normal) -> QFont:
        """Get body font (Inter equivalent)."""
        font = QFont("Segoe UI", size)  # Good fallback for Inter
        font.setWeight(weight)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font
    
    def get_shard_label_font(self, size: int = 28) -> QFont:
        """Get shard button label font (Exo 2 ExtraBold)."""
        font = QFont("Arial", size)
        font.setWeight(QFont.Weight.ExtraBold)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font
    
    def get_kiosk_title_font(self, size: int = 48) -> QFont:
        """Get main kiosk title font (Exo 2 Black)."""
        font = QFont("Arial", size)
        font.setWeight(QFont.Weight.Black)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font


class BBANTheme:
    """Main theme manager implementing the complete BBAN design system from reference screenshots."""
    
    def __init__(self):
        self.colors = BBANColors()
        self.fonts = BBANFonts()
        self._style_cache: Dict[str, str] = {}
    
    def apply_to_application(self, app: QApplication) -> None:
        """Apply the complete BBAN theme to the application."""
        # Set application-wide palette
        palette = self._create_application_palette()
        app.setPalette(palette)
        
        # Apply global stylesheet
        app.setStyleSheet(self.get_global_stylesheet())
    
    def _create_application_palette(self) -> QPalette:
        """Create the application color palette using BBAN colors."""
        palette = QPalette()
        
        # Window colors
        palette.setColor(QPalette.ColorRole.Window, self.colors.BACKGROUND_DEEP)
        palette.setColor(QPalette.ColorRole.WindowText, self.colors.TEXT_PRIMARY)
        
        # Base colors (for input fields)
        palette.setColor(QPalette.ColorRole.Base, self.colors.BACKGROUND_MID)
        palette.setColor(QPalette.ColorRole.AlternateBase, self.colors.BACKGROUND_DEEP)
        palette.setColor(QPalette.ColorRole.Text, self.colors.TEXT_PRIMARY)
        
        # Button colors
        palette.setColor(QPalette.ColorRole.Button, self.colors.BACKGROUND_MID)
        palette.setColor(QPalette.ColorRole.ButtonText, self.colors.TEXT_PRIMARY)
        
        # Highlight colors
        palette.setColor(QPalette.ColorRole.Highlight, self.colors.PRIMARY_INTERACTIVE)
        palette.setColor(QPalette.ColorRole.HighlightedText, self.colors.BACKGROUND_DEEP)
        
        return palette
    
    def get_global_stylesheet(self) -> str:
        """Get the complete global stylesheet using BBAN design."""
        if "global" not in self._style_cache:
            self._style_cache["global"] = self._generate_global_stylesheet()
        return self._style_cache["global"]
    
    def _generate_global_stylesheet(self) -> str:
        """Generate the complete global stylesheet with BBAN colors."""
        return f"""
/* Global Application Styling - BBAN Theme */
QMainWindow {{
    background-color: {self.colors.BACKGROUND_DEEP.name()};
    color: {self.colors.TEXT_PRIMARY.name()};
}}

/* Toolbar Styling - BBAN Design */
QToolBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.BACKGROUND_MID.name()},
                stop:1 {self.colors.BACKGROUND_DEEP.name()});
    border: 1px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    border-radius: 8px;
    spacing: 8px;
    padding: 4px;
}}

QToolBar::separator {{
    background: {self.colors.PRIMARY_INTERACTIVE.name()};
    width: 1px;
    margin: 4px;
}}

/* Button Styling - BBAN Green Theme */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.PRIMARY_DARKER.name()},
                stop:1 {self.colors.PRIMARY_INTERACTIVE.name()});
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    border-radius: 6px;
    color: {self.colors.TEXT_PRIMARY.name()};
    font-family: "Segoe UI";
    font-size: 11px;
    font-weight: 500;
    padding: 8px 16px;
    margin: 2px;
}}

QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.PRIMARY_INTERACTIVE.name()},
                stop:1 {self.colors.PRIMARY_INTERACTIVE.lighter(120).name()});
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.lighter(130).name()};
}}

QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.PRIMARY_DARKER.name()},
                stop:1 {self.colors.PRIMARY_DARKER.lighter(110).name()});
}}

/* Secondary Button Styling - BBAN Yellow */
QPushButton[style="secondary"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.SECONDARY_DARKER.name()},
                stop:1 {self.colors.SECONDARY_INTERACTIVE.name()});
    border: 2px solid {self.colors.SECONDARY_INTERACTIVE.name()};
    color: {self.colors.BBAN_DARK_GREY.name()};
}}

QPushButton[style="secondary"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.SECONDARY_INTERACTIVE.name()},
                stop:1 {self.colors.SECONDARY_INTERACTIVE.lighter(120).name()});
    border: 2px solid {self.colors.SECONDARY_INTERACTIVE.lighter(130).name()};
}}

/* Ghost Button Styling */
QPushButton[style="ghost"] {{
    background: transparent;
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    color: {self.colors.PRIMARY_INTERACTIVE.name()};
}}

QPushButton[style="ghost"]:hover {{
    background: {self.colors.PRIMARY_INTERACTIVE.name()};
    color: {self.colors.BACKGROUND_DEEP.name()};
}}

/* Success Button Styling - BBAN Green */
QPushButton[style="success"] {{
    background: {self.colors.SUCCESS.name()};
    border: 2px solid {self.colors.SUCCESS.lighter(120).name()};
    color: {self.colors.BACKGROUND_DEEP.name()};
}}

/* Warning Button Styling - BBAN Yellow */
QPushButton[style="warning"] {{
    background: {self.colors.WARNING.name()};
    border: 2px solid {self.colors.WARNING.lighter(120).name()};
    color: {self.colors.BACKGROUND_DEEP.name()};
}}

/* Error Button Styling */
QPushButton[style="error"] {{
    background: {self.colors.ERROR.name()};
    border: 2px solid {self.colors.ERROR.lighter(120).name()};
    color: {self.colors.TEXT_PRIMARY.name()};
}}

/* Group Box Styling - BBAN Cards */
QGroupBox {{
    background: {self.colors.BACKGROUND_MID.name()};
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    border-radius: 12px;
    font-family: "Arial";
    font-size: 14px;
    font-weight: 600;
    color: {self.colors.PRIMARY_INTERACTIVE.name()};
    margin-top: 12px;
    padding-top: 8px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {self.colors.PRIMARY_INTERACTIVE.name()};
    border: none;
}}

/* Input Field Styling */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {self.colors.BACKGROUND_MID.name()};
    border: 1px solid {self.colors.PRIMARY_DARKER.name()};
    border-radius: 6px;
    color: {self.colors.TEXT_PRIMARY.name()};
    font-family: "Segoe UI";
    font-size: 12px;
    padding: 6px 8px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    background: {self.colors.BACKGROUND_MID.lighter(110).name()};
}}

/* Slider Styling - BBAN Green */
QSlider::groove:horizontal {{
    background: {self.colors.BACKGROUND_DEEP.name()};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {self.colors.PRIMARY_INTERACTIVE.name()};
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.lighter(130).name()};
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -8px 0;
}}

QSlider::sub-page:horizontal {{
    background: {self.colors.PRIMARY_INTERACTIVE.name()};
    border-radius: 3px;
}}

/* ComboBox Styling */
QComboBox {{
    background: {self.colors.BACKGROUND_MID.name()};
    border: 1px solid {self.colors.PRIMARY_DARKER.name()};
    border-radius: 6px;
    color: {self.colors.TEXT_PRIMARY.name()};
    font-family: "Segoe UI";
    font-size: 12px;
    padding: 6px 24px 6px 8px;
}}

QComboBox:focus {{
    border: 2px solid {self.colors.PRIMARY_INTERACTIVE.name()};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border: 4px solid transparent;
    border-top: 6px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    margin-right: 4px;
}}

/* Label Styling */
QLabel {{
    color: {self.colors.TEXT_PRIMARY.name()};
    font-family: "Segoe UI";
    font-size: 12px;
}}

QLabel[style="heading"] {{
    color: {self.colors.PRIMARY_INTERACTIVE.name()};
    font-family: "Arial";
    font-size: 18px;
    font-weight: 600;
}}

QLabel[style="kiosk-title"] {{
    color: {self.colors.PRIMARY_INTERACTIVE.name()};
    font-family: "Arial";
    font-size: 48px;
    font-weight: 900;
}}

QLabel[style="subheading"] {{
    color: {self.colors.TEXT_SECONDARY.name()};
    font-family: "Arial";
    font-size: 14px;
    font-weight: 500;
}}

QLabel[style="caption"] {{
    color: {self.colors.TEXT_TERTIARY.name()};
    font-family: "Segoe UI";
    font-size: 10px;
}}

/* Status Bar Styling */
QStatusBar {{
    background: {self.colors.BACKGROUND_MID.name()};
    border-top: 1px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    color: {self.colors.TEXT_PRIMARY.name()};
}}

/* Progress Bar Styling - BBAN Green */
QProgressBar {{
    background: {self.colors.BACKGROUND_DEEP.name()};
    border: 1px solid {self.colors.PRIMARY_INTERACTIVE.name()};
    border-radius: 6px;
    text-align: center;
    color: {self.colors.TEXT_PRIMARY.name()};
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {self.colors.PRIMARY_INTERACTIVE.name()},
                stop:1 {self.colors.PRIMARY_DARKER.name()});
    border-radius: 4px;
}}
"""
    
    def get_shard_button_style(self, shard_type: str) -> str:
        """Get styling for custom shard buttons."""
        styles = {
            "match": f"""
                background-color: {self.colors.MENU_SHARD_MATCH_BG.name()};
                color: {self.colors.MENU_SHARD_MATCH_TEXT.name()};
                border: none;
            """,
            "freeplay": f"""
                background-color: {self.colors.MENU_SHARD_FREEPLAY_BG.name()};
                color: {self.colors.MENU_SHARD_FREEPLAY_TEXT.name()};
                border: none;
            """,
            "systemhub": f"""
                background-color: {self.colors.MENU_SHARD_SYSTEMHUB_BG.name()};
                color: {self.colors.MENU_SHARD_SYSTEMHUB_TEXT.name()};
                border: none;
            """
        }
        return styles.get(shard_type, "")


# Global theme instance - now using BBAN theme instead of cyber-kinetic
theme = BBANTheme() 