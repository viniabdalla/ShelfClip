import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
import main

app = QApplication(sys.argv)
app.setFont(QFont("Segoe UI", 10))
app.setQuitOnLastWindowClosed(False)

print("creating ShelfWindow...", flush=True)
win = main.ShelfWindow()
print("ShelfWindow OK - entering event loop", flush=True)
win.show()
sys.exit(app.exec())
