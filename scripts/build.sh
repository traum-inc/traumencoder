appname=traumenc

uname=`uname`
if [ $uname = 'Darwin' ]; then
    build_arch=mac64
elif [ $uname = 'Linux' ]; then
    build_arch=lnx64
else
    echo "Unknown platform '$uname'."
    exit 1
fi

build_id=`git rev-parse --short HEAD`
build_date=`date +%y%m%d`
build_basename=${appname}-${build_date}-${build_id}-${build_arch}


echo "Cleaning dist."
(cd dist &&
    rm -rf ${appname}*)


echo "Building ${appname} with PyInstaller."

pyinstaller -y \
    --add-data="config.ini:." \
    --add-data="icons:icons" \
    --add-data="bin:bin" \
    --windowed \
    --noupx \
    -p $appname \
    -n $appname \
    $appname/__main__.py

if [ $uname = 'Darwin' ]; then
    echo "Creating disk image ${build_basename}.dmg"
    (cd dist &&
        mkdir ${build_basename} &&
        mv ${appname}.app ${build_basename}/ &&
        hdiutil create -srcfolder ${build_basename} -volname ${build_basename}  ${build_basename}.dmg)
else
    echo "Creating tarball ${build_basename}.tar.gz"
    (cd dist &&
        tar cfvz ${build_basename}.tar.gz ${appname})
fi

echo "Build complete."
