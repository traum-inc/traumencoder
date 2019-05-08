pyinstaller -y -n traumenc --add-data="config.ini:." --add-data="icons:icons" --add-data="bin:bin" --windowed --noupx -p traumenc traumenc/__main__.py
