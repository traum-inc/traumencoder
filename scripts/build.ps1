$appname = "traumenc"

echo "Cleaning dist."
Remove-Item -Recurse dist\$appname*

echo "Building $appname with PyInstaller."

pyinstaller -y `
    --add-data="config.ini;." `
    --add-data="icons;icons" `
    --add-data="bin;bin" `
    --windowed `
    --noupx `
    -p $appname `
    -n $appname `
    $appname\__main__.py

$build_id = (git rev-parse --short HEAD)
$build_date = (Get-Date).tostring("yyMMdd")
$build_basename = "${appname}-${build_date}-${build_id}"

echo "Creating archive ${build_basename}.zip"
Compress-Archive -Path dist\$appname -DestinationPath dist\$build_basename.zip

echo "Build complete."
