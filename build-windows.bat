rmdir /S /Q dist

pyinstaller --noupx --onefile --noconfirm ^
	--exclude-module Tkconstants ^
	--exclude-module Tkinter ^
	--exclude-module matplotlib ^
	--name sushi ^
	sushi/__main__.py

mkdir dist\licenses
copy /Y licenses\* dist\licenses\*
copy LICENSE dist\licenses\Sushi.txt
copy README.md dist\readme.md
