"""Сборка легкого Windows-приложения без Dear PyGui и без картинок."""
from pathlib import Path
import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent

PyInstaller.__main__.run([
    str(ROOT / "main.py"),
    "--name=SeaBattleLite",
    "--onefile",
    "--windowed",
    "--clean",
    "--exclude-module=dearpygui",
    "--exclude-module=numpy",
    "--exclude-module=scipy",
    "--exclude-module=matplotlib",
    "--exclude-module=cryptography",
    "--exclude-module=unittest",
    "--exclude-module=pydoc",
    "--exclude-module=pydoc_data",
    "--exclude-module=setuptools",
    "--exclude-module=distutils",
    "--exclude-module=pip",
    "--exclude-module=pygame",
    "--exclude-module=sqlite3",
    "--exclude-module=test",
    f"--distpath={ROOT / 'dist'}",
    f"--workpath={ROOT / 'build'}",
    f"--specpath={ROOT}",
])
