import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception:
        # 捕获所有未处理异常并弹窗显示
        error_msg = traceback.format_exc()
        try:
            QMessageBox.critical(None, "程序崩溃", f"发生未捕获的异常:\n\n{error_msg}")
        except:
            # 如果连弹窗都失败（例如QApplication未初始化），则写入文件
            with open("crash.log", "w") as f:
                f.write(error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
